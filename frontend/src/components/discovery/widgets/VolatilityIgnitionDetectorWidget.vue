<template>
  <div class="vid-root">
    <div class="vid-header">
      <span class="vid-title">Volatility Ignition Detector</span>
      <div class="vid-controls">
        <span class="vid-underlying">{{ shortUnderlying }}</span>
        <button type="button" class="vid-btn" :class="{ loading }" :disabled="loading" @click="reload">
          {{ loading ? '...' : 'Reload' }}
        </button>
      </div>
    </div>

    <div v-if="error && !snapshot" class="vid-empty">{{ error }}</div>
    <div v-else-if="loading && !snapshot" class="vid-empty">Loading ignition inputs...</div>
    <div v-else-if="!snapshot" class="vid-empty">Waiting for enough IV, flow and structure data.</div>

    <template v-else>
      <div class="vid-top-grid">
        <div class="vid-hero-card">
          <div class="vid-hero-head">
            <div class="vid-gauge" :style="gaugeStyle">
              <div class="vid-gauge-inner">
                <span class="vid-gauge-score">{{ formatScore(snapshot.score) }}</span>
                <span class="vid-gauge-max">/100</span>
              </div>
            </div>

            <div class="vid-hero-copy">
              <div class="vid-hero-meta">
                <span class="vid-state" :class="snapshot.stateTone">{{ snapshot.state }}</span>
                <span class="vid-direction" :class="snapshot.directionTone">{{ snapshot.direction }}</span>
              </div>
              <div class="vid-reading">{{ snapshot.reading }}</div>
              <div class="vid-trigger-row">
                <span>Principal gatilho: <b>{{ snapshot.principalTrigger }}</b></span>
                <span>Futuro: <b>{{ snapshot.futureConfirmationLabel }}</b></span>
              </div>
              <div class="vid-level-row">
                <span>Confirmacao: <b>{{ snapshot.confirmationText }}</b></span>
                <span>Invalidacao: <b>{{ snapshot.invalidationText }}</b></span>
              </div>
            </div>
          </div>

          <div class="vid-hero-foot">
            <span>{{ snapshot.marketLabel }}</span>
            <span>{{ snapshot.sessionStamp }}</span>
          </div>
        </div>

        <div class="vid-kpi-grid">
          <div class="vid-kpi">
            <span class="vid-kpi-label">IV ATM</span>
            <span class="vid-kpi-value">{{ pct(snapshot.ivAtm) }}</span>
            <span class="vid-kpi-sub" :class="deltaTone(snapshot.ivDelta15mPts)">{{ signed(snapshot.ivDelta15mPts, 2) }} pts / 15m</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Vol of vol</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.surfaceMotionScore) }}</span>
            <span class="vid-kpi-sub" :class="deltaTone(snapshot.surfaceMotionDelta)">{{ signed(snapshot.surfaceMotionDelta, 1) }} vs 15m</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">RV accel</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.realizedVolAccelerationScore) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.rvLabel }}</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Gamma fragility</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.gammaFragilityScore) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.gammaLabel }}</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Pinning vs expansion</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.expansionScore) }} / {{ formatScore(snapshot.pinningScore) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.pinExpLabel }}</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Dealer pain</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.dealerPainScore) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.dealerLabel }}</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Future confirm</span>
            <span class="vid-kpi-value">{{ formatScore(snapshot.futureAggressionConfirmationScore) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.futureConfirmationLabel }}</span>
          </div>
          <div class="vid-kpi">
            <span class="vid-kpi-label">Spot</span>
            <span class="vid-kpi-value">{{ formatLevel(snapshot.spot) }}</span>
            <span class="vid-kpi-sub">{{ snapshot.structureLabel }}</span>
          </div>
        </div>
      </div>

      <div v-if="snapshot.alerts.length" class="vid-alerts">
        <span v-for="alert in snapshot.alerts" :key="alert" class="vid-alert-pill">{{ alert }}</span>
      </div>

      <div class="vid-mid-grid">
        <div class="vid-panel">
          <div class="vid-panel-head">
            <span class="vid-panel-title">Checklist de ignicao</span>
            <span class="vid-panel-sub">o que esta ou nao confirmado</span>
          </div>
          <div class="vid-checklist">
            <div v-for="item in snapshot.checklist" :key="item.key" class="vid-check-row" :class="item.tone">
              <span class="vid-check-mark">{{ item.active ? 'x' : item.partial ? '!' : ' ' }}</span>
              <div class="vid-check-copy">
                <span class="vid-check-label">{{ item.label }}</span>
                <span class="vid-check-note">{{ item.note }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="vid-panel">
          <div class="vid-panel-head">
            <span class="vid-panel-title">Motores do score</span>
            <span class="vid-panel-sub">blend estrutural e intraday</span>
          </div>
          <div v-for="item in snapshot.components" :key="item.key" class="vid-factor-row">
            <span class="vid-factor-name">{{ item.label }}</span>
            <div class="vid-factor-track">
              <div class="vid-factor-bar" :class="item.tone" :style="{ width: `${clamp(item.score, 0, 100)}%` }"></div>
            </div>
            <span class="vid-factor-score">{{ formatScore(item.score) }}</span>
          </div>
        </div>
      </div>

      <div class="vid-history-block">
        <div class="vid-panel-head">
          <span class="vid-panel-title">Historico intraday</span>
          <div class="vid-history-head-meta">
            <span class="vid-panel-sub">{{ historyLabel }}</span>
            <span v-if="displayHistoryPoint" class="vid-history-chip">
              {{ historyHoverPoint ? 'Hover' : 'Latest' }} · {{ displayHistoryPoint.axisLabel }} · {{ formatScore(displayHistoryPoint.score) }} · {{ displayHistoryPoint.state }}
            </span>
          </div>
        </div>
        <div class="vid-history-wrap">
          <div class="vid-history-side">
            <div v-if="displayHistoryPoint" class="vid-history-tooltip vid-history-tooltip-fixed">
              <div class="vid-history-tooltip-mode">{{ historyHoverPoint ? 'Hover' : 'Latest' }}</div>
              <div class="vid-history-tooltip-time">{{ displayHistoryPoint.axisLabel }}</div>
              <div class="vid-history-tooltip-row">
                <span>{{ displayHistoryPoint.state }}</span>
                <span>{{ displayHistoryPoint.directionLabel }}</span>
              </div>
              <div class="vid-history-tooltip-row">
                <span>Score {{ formatScore(displayHistoryPoint.score) }}</span>
                <span>{{ displayHistoryPoint.signalLabel !== 'No signal' ? displayHistoryPoint.signalLabel : displayHistoryPoint.triggerLabel }}</span>
              </div>
              <div class="vid-history-tooltip-row">
                <span>Surface {{ formatScore(displayHistoryPoint.surfaceShockScore) }}</span>
                <span>Transmission {{ formatScore(displayHistoryPoint.transmissionScore) }}</span>
              </div>
              <div class="vid-history-tooltip-row">
                <span>{{ displayHistoryPoint.signalReason || displayHistoryPoint.triggerLabel }}</span>
                <span>{{ displayHistoryPoint.triggerLabel }}</span>
              </div>
            </div>
            <div v-else class="vid-history-tooltip vid-history-tooltip-fixed vid-history-tooltip-empty">
              <div class="vid-history-tooltip-mode">History</div>
              <div class="vid-history-tooltip-time">Waiting for data</div>
              <div class="vid-history-tooltip-row">
                <span>Passe o mouse no intraday</span>
                <span>1m</span>
              </div>
            </div>
          </div>
          <div class="vid-history-chart" ref="historyWrap">
            <template v-if="historySeries.length > 1">
              <canvas
                ref="historyCanvas"
                class="vid-history-canvas"
                @mouseenter="handleHistoryEnter"
                @mousemove="handleHistoryMove"
                @mouseleave="handleHistoryLeave"
              ></canvas>
            </template>
            <div v-else class="vid-history-empty">Waiting for 1m history from today.</div>
          </div>
        </div>
        <div class="vid-history-footer">
          <span class="vid-line-key"><i class="vid-line-chip score"></i> Score</span>
          <span class="vid-line-key"><i class="vid-line-chip surface"></i> Surface shock</span>
          <span class="vid-line-key"><i class="vid-line-chip transmission"></i> Transmission</span>
          <span class="vid-line-key"><i class="vid-line-chip watch"></i> 55</span>
          <span class="vid-line-key"><i class="vid-line-chip expand"></i> 70</span>
          <span class="vid-line-key"><i class="vid-line-chip pulse"></i> watch pulse</span>
          <span class="vid-line-key"><i class="vid-line-chip confirm"></i> entrada em ignition/expansion</span>
          <span class="vid-line-key"><i class="vid-line-chip marker up"></i> cruza para cima</span>
          <span class="vid-line-key"><i class="vid-line-chip marker down"></i> perde limiar</span>
        </div>
      </div>

      <div class="vid-footer-note">
        Vega buying pressure e future confirmation usam proxy intraday de fluxo de opcoes, prazo, delta, price action do XB1 e estrutura de gamma ja disponivel na Discovery.
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getLiveCaptureWorkbookLatest, getLiveCaptureWorkbookSeries, getVolIndexHistory, getVolumeActivity } from '@/api/options'

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

const WINDOW_5 = { minutes: 5, weight: 0.40 }
const WINDOW_15 = { minutes: 15, weight: 0.60 }
const AUTO_REFRESH_MS = 120_000
const MIN_FETCH_INTERVAL_MS = 75_000
const HISTORY_HEIGHT = 186
const HISTORY_PAD = { top: 16, right: 14, bottom: 30, left: 46 }
const FUTURE_SECURITY = 'XB1 Index'
const SPOT_SECURITY = 'IBOV Index'
const SESSION_TIMEZONE = 'America/Sao_Paulo'
const SESSION_START_MINUTES = (9 * 60)
const SESSION_END_MINUTES = (18 * 60) + 30

const STATE_META = {
  OFF: { tone: 'off', color: '#64748b' },
  Watch: { tone: 'watch', color: '#f59e0b' },
  Ignition: { tone: 'ignition', color: '#fb923c' },
  Expansion: { tone: 'expansion', color: '#ef4444' },
  Exhaustion: { tone: 'exhaustion', color: '#a78bfa' },
}

const DIRECTION_META = {
  upside: { label: 'Upside Ignition', tone: 'up' },
  downside: { label: 'Downside Ignition', tone: 'down' },
  vol_only: { label: 'Vol-Only Ignition', tone: 'neutral' },
  two_sided: { label: 'Two-Sided Vol Ignition', tone: 'mixed' },
}

const loading = ref(false)
const error = ref(null)
const dailyHistory = ref([])
const intradayHistory = ref([])
const flowEvents = ref([])
const futurePriceHistory = ref([])
const spotPriceHistory = ref([])
const historyWrap = ref(null)
const historyCanvas = ref(null)
const historyHoverIndex = ref(null)
const historyMetrics = ref(null)

const sessionMinuteFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: SESSION_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

let refreshTimer = null
let resizeHandler = null
let lastLoadAt = 0

const underlying = computed(() => props.underlyingSecurity || props.modelData?.underlying_security || 'IBOVE Index')
const shortUnderlying = computed(() => String(underlying.value || '').replace(/\s+Index$/i, '') || 'IBOV')

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

function median(values) {
  if (!values.length) return null
  const sorted = values
    .map(value => safeNumber(value))
    .filter(value => value != null)
    .sort((left, right) => left - right)
  if (!sorted.length) return null
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) return (sorted[middle - 1] + sorted[middle]) / 2
  return sorted[middle]
}

function delay(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

function std(values) {
  if (values.length < 2) return null
  const avg = mean(values)
  if (avg == null) return null
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length
  return Math.sqrt(Math.max(variance, 0))
}

function weightedScore(entries) {
  let totalWeight = 0
  let total = 0
  for (const entry of entries) {
    const score = clamp(entry?.score ?? 0, 0, 100)
    const weight = Number(entry?.weight ?? 0)
    if (!Number.isFinite(weight) || weight <= 0) continue
    total += score * weight
    totalWeight += weight
  }
  return totalWeight > 0 ? total / totalWeight : 0
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

function mad(values, center = null) {
  const resolvedCenter = center ?? median(values)
  if (resolvedCenter == null) return null
  const deviations = values
    .map(value => safeNumber(value))
    .filter(value => value != null)
    .map(value => Math.abs(value - resolvedCenter))
  return deviations.length ? median(deviations) : null
}

function robustCenterScale(values, fallbackScale = 1) {
  const clean = values
    .map(value => safeNumber(value))
    .filter(value => value != null)
  if (!clean.length) {
    return {
      center: 0,
      scale: Math.max(fallbackScale, 1e-6),
    }
  }
  const center = median(clean) ?? 0
  const robustMad = mad(clean, center)
  const robustSigma = robustMad != null && robustMad > 1e-9 ? robustMad * 1.4826 : null
  const sigma = robustSigma ?? std(clean) ?? fallbackScale
  return {
    center,
    scale: Math.max(sigma || fallbackScale, fallbackScale, 1e-6),
  }
}

function buildLagDiffs(values, lag = 1, scale = 1) {
  const diffs = []
  if (!Array.isArray(values) || values.length <= lag || lag < 1) return diffs
  for (let index = lag; index < values.length; index += 1) {
    const previous = safeNumber(values[index - lag])
    const current = safeNumber(values[index])
    if (previous == null || current == null) continue
    diffs.push((current - previous) * scale)
  }
  return diffs
}

function adaptiveShockScore(value, sample, {
  absolute = false,
  positive = false,
  bias = 0.30,
  fallbackScale = 1,
} = {}) {
  const numeric = safeNumber(value)
  if (numeric == null) return 0
  const target = absolute ? Math.abs(numeric) : numeric
  if (positive && target <= 0) return 0
  const clean = (sample || [])
    .map(item => safeNumber(item))
    .filter(item => item != null)
    .map(item => (absolute ? Math.abs(item) : item))
    .filter(item => (positive ? item > 0 : true))
  const { center, scale } = robustCenterScale(clean, fallbackScale)
  const z = (target - center) / scale
  return clamp((scoreFromZ(z - bias) * 1.12) - 12, 0, 100)
}

function blendScores(baseScore, adaptiveScore, adaptiveWeight = 0.5) {
  return weightedScore([
    { score: baseScore, weight: Math.max(1 - adaptiveWeight, 0) },
    { score: adaptiveScore, weight: Math.max(adaptiveWeight, 0) },
  ])
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

function signedDirectionalScore(value, pivot) {
  if (!Number.isFinite(value) || pivot <= 0) return { up: 0, down: 0 }
  return {
    up: clamp((value / pivot) * 100, 0, 100),
    down: clamp((-value / pivot) * 100, 0, 100),
  }
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

function normalizeVolRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || normalized.reference_price_at || '').trim()
  const date = String(normalized.date || capturedAt.slice(0, 10) || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  normalized.captured_at = capturedAt || null
  normalized.date = date || null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = date || null
  normalized._price = safeNumber(normalized.reference_price ?? normalized.spot ?? normalized.reference_spot)
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
  normalized._vega = safeNumber(normalized.vega)
  return normalized
}

function normalizeWorkbookSeriesRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  const sessionDate = String(normalized.session_date || normalized.date || capturedAt.slice(0, 10) || '').trim() || null
  const rawValue = safeNumber(normalized.raw_value)
  normalized.captured_at = capturedAt || null
  normalized.session_date = sessionDate
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = sessionDate
  normalized.raw_value = rawValue
  normalized._price = rawValue
  normalized.daily_change_pct = safeNumber(normalized.daily_change_pct)
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
      const restMean = mean(values.slice(1))
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
    if (epoch == null || !isWithinSessionWindow(epoch)) continue
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

function sessionMinutesForEpoch(epoch) {
  if (!Number.isFinite(epoch)) return null
  const parts = sessionMinuteFormatter.formatToParts(new Date(epoch))
  const hour = Number(parts.find(part => part.type === 'hour')?.value ?? NaN)
  const minute = Number(parts.find(part => part.type === 'minute')?.value ?? NaN)
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null
  return (hour * 60) + minute
}

function isWithinSessionWindow(epoch) {
  const minutes = sessionMinutesForEpoch(epoch)
  if (minutes == null) return false
  return minutes >= SESSION_START_MINUTES && minutes <= SESSION_END_MINUTES
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
    VOV_COMPONENTS.forEach(component => {
      const z = computeZScore(rawSeries[component.key][index], stats[component.key])
      totalWeight += component.weight
      totalZ += component.weight * z
    })
    scoreSeries.push({
      epoch: records[index]?._epoch,
      timestamp: records[index]?.captured_at || null,
      z: totalWeight > 0 ? totalZ / totalWeight : 0,
      score: scoreFromZ(totalWeight > 0 ? totalZ / totalWeight : 0),
    })
  }
  return {
    scoreSeries,
    latest: scoreSeries[scoreSeries.length - 1] || null,
  }
}

function nearestByMinutes(series, targetMinutesAgo) {
  if (!series.length) return null
  const latestEpoch = series[series.length - 1]?._epoch ?? series[series.length - 1]?.epoch
  if (latestEpoch == null) return null
  const targetEpoch = latestEpoch - (targetMinutesAgo * 60 * 1000)
  for (let index = series.length - 1; index >= 0; index -= 1) {
    const item = series[index]
    const epoch = item?._epoch ?? item?.epoch
    if (epoch != null && epoch <= targetEpoch) return item
  }
  return series[0] || null
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

function accelerationMetrics(levels, mode = 'diff', floor = 0.001) {
  const filtered = levels.filter(value => value != null)
  const steps = buildReturns(filtered, mode)
  if (!steps.length) {
    return { score: 0, current: 0, average: 0, z: 0, negativeScore: 0 }
  }
  const current = steps[steps.length - 1] || 0
  const baseline = steps.slice(0, -1)
  const average = mean(baseline) || 0
  const dispersion = Math.max(std(baseline) || 0, floor)
  const delta = current - average
  return {
    score: clamp((Math.max(delta, 0) / dispersion) * 52, 0, 100),
    current,
    average,
    z: delta / dispersion,
    negativeScore: clamp((Math.max(-delta, 0) / dispersion) * 52, 0, 100),
  }
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

function withLocalTimeout(promise, label, timeoutMs = 15_000) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error(`${label} timeout`)), timeoutMs)
    }),
  ])
}

function cacheKey(kind, underlyingValue) {
  return `discovery:vid:${kind}:${String(underlyingValue || 'IBOVE Index')}`
}

function readCache(kind, underlyingValue) {
  try {
    const raw = window.localStorage.getItem(cacheKey(kind, underlyingValue))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function writeCache(kind, underlyingValue, payload) {
  try {
    window.localStorage.setItem(cacheKey(kind, underlyingValue), JSON.stringify(payload))
  } catch {
    // best effort only
  }
}

function cachedWorkbookRowsForSession(cachedRows, sessionDate) {
  const rows = Array.isArray(cachedRows) ? cachedRows : []
  if (!rows.length || !sessionDate) return []
  const hasSession = rows
    .map(normalizeWorkbookSeriesRecord)
    .some(row => row._sessionDate === sessionDate)
  return hasSession ? rows : []
}

function mergeWorkbookRows(existingRows, latestRow) {
  const merged = new Map()
  for (const row of Array.isArray(existingRows) ? existingRows : []) {
    const capturedAt = String(row?.captured_at || '').trim()
    if (capturedAt) merged.set(capturedAt, row)
  }
  const latestCapturedAt = String(latestRow?.captured_at || '').trim()
  if (latestCapturedAt) merged.set(latestCapturedAt, latestRow)
  return Array.from(merged.values()).sort((left, right) => {
    const leftTime = new Date(left?.captured_at || 0).getTime()
    const rightTime = new Date(right?.captured_at || 0).getTime()
    return leftTime - rightTime
  })
}

function readVolOfVolCache(underlyingValue) {
  try {
    const key = `discovery:vov:vol:${String(underlyingValue || '').trim() || 'unknown'}`
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || !Array.isArray(parsed.records)) return null
    return {
      daily_history: [],
      intraday_history: parsed.records,
    }
  } catch {
    return null
  }
}

const latestSessionDate = computed(() => {
  const last = intradayHistory.value[intradayHistory.value.length - 1]
  return last?._sessionDate || null
})

const intradayMinuteHistory = computed(() => bucketRecordsByMinute(intradayHistory.value))
const futureMinuteHistory = computed(() => bucketRecordsByMinute(futurePriceHistory.value))
const spotMinuteHistory = computed(() => bucketRecordsByMinute(spotPriceHistory.value))

const sessionHistory = computed(() => {
  const sessionDate = latestSessionDate.value
  if (!sessionDate) return []
  const futureMap = new Map(
    futureMinuteHistory.value
      .filter(item => item._sessionDate === sessionDate && item._epoch != null)
      .map(item => [item._epoch, item]),
  )
  const spotMap = new Map(
    spotMinuteHistory.value
      .filter(item => item._sessionDate === sessionDate && item._epoch != null)
      .map(item => [item._epoch, item]),
  )
  return intradayMinuteHistory.value
    .filter(item => item._sessionDate === sessionDate)
    .map(item => {
      const futureRecord = futureMap.get(item._epoch) || null
      const spotRecord = spotMap.get(item._epoch) || null
      const futurePrice = safeNumber(futureRecord?.raw_value ?? futureRecord?._price)
      const spotPrice = safeNumber(spotRecord?.raw_value ?? spotRecord?._price ?? item.spot ?? item.reference_spot)
      return {
        ...item,
        _future_price: futurePrice,
        _spot_price: spotPrice,
        _price: safeNumber(item._price) ?? futurePrice ?? spotPrice,
      }
    })
})

const sessionFlow = computed(() => {
  const sessionDate = latestSessionDate.value
  return flowEvents.value
    .filter(item => (sessionDate ? item._sessionDate === sessionDate : true))
    .filter(item => item._epoch != null && isWithinSessionWindow(item._epoch))
    .filter(item => item._epoch != null && item._volume > 0)
    .sort((left, right) => (left._epoch || 0) - (right._epoch || 0))
})

const marketContext = computed(() => props.modelData?.market_context ?? {})
const aggregates = computed(() => props.modelData?.aggregates ?? {})
const pressure = computed(() => props.modelData?.pressure ?? {})

const baseByStrike = computed(() => {
  const rows = aggregates.value?.by_strike ?? []
  return rows
    .map(row => {
      const strike = safeNumber(row.strike ?? row.key)
      const gex = safeNumber(row.gex) || 0
      const callOi = safeNumber(row.call_oi) || 0
      const putOi = safeNumber(row.put_oi) || 0
      const vex = safeNumber(row.vex) || 0
      const cex = safeNumber(row.cex) || 0
      return {
        strike,
        gex,
        callOi,
        putOi,
        totalOi: callOi + putOi,
        vex,
        cex,
      }
    })
    .filter(row => row.strike != null && row.totalOi > 0)
    .sort((left, right) => left.strike - right.strike)
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

function nearestZeroCross(points, field) {
  const rows = Array.isArray(points) ? points : []
  let best = null
  for (let index = 1; index < rows.length; index += 1) {
    const prev = rows[index - 1]
    const next = rows[index]
    const prevSpot = safeNumber(prev?.spot ?? prev?.strike)
    const nextSpot = safeNumber(next?.spot ?? next?.strike)
    const prevValue = safeNumber(prev?.[field])
    const nextValue = safeNumber(next?.[field])
    if (prevSpot == null || nextSpot == null || prevValue == null || nextValue == null) continue
    if (prevValue === 0) return prevSpot
    if (nextValue === 0) return nextSpot
    if ((prevValue < 0 && nextValue > 0) || (prevValue > 0 && nextValue < 0)) {
      const ratio = Math.abs(prevValue) / (Math.abs(prevValue) + Math.abs(nextValue))
      const level = prevSpot + ((nextSpot - prevSpot) * ratio)
      if (best == null || Math.abs(level) < Math.abs(best)) best = level
    }
  }
  return best
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
    const strength = (0.60 * (row.totalOi / meta.maxOi)) + (0.40 * (Math.abs(row.gex) / meta.maxAbsRowGex))
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

function bestWall(meta, spot, direction) {
  const candidates = meta.rows.filter(row => direction > 0 ? row.strike >= spot : row.strike <= spot)
  let best = null
  for (const row of candidates) {
    const strength = (0.60 * (row.totalOi / meta.maxOi)) + (0.40 * (Math.abs(row.gex) / meta.maxAbsRowGex))
    const distance = Math.abs(row.strike - spot)
    const score = strength * clamp(1 - (distance / Math.max(spot * 0.02, 4000)), 0, 1)
    if (!best || score > best.score) best = { strike: row.strike, score, totalOi: row.totalOi, gex: row.gex, distance }
  }
  return best
}

const dexNeutralLevel = computed(() => nearestZeroCross(pressure.value?.curve ?? [], 'dex'))

const structureMeta = computed(() => {
  const rows = baseByStrike.value
  const totalOi = rows.reduce((sum, row) => sum + row.totalOi, 0)
  const totalAbsGex = rows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const maxOi = Math.max(...rows.map(row => row.totalOi), 1)
  const maxAbsRowGex = Math.max(...rows.map(row => Math.abs(row.gex)), 1)
  const gammaFlipPoints = (props.modelData?.gamma_flip_history?.latest_flip_points ?? [])
    .map(value => safeNumber(value))
    .filter(value => value != null)
  return {
    rows,
    totalOi,
    totalAbsGex,
    maxOi,
    maxAbsRowGex,
    totals: aggregates.value?.totals ?? {},
    pinningBand: pressure.value?.pinning_band ?? {},
    accelerationBand: pressure.value?.acceleration_band ?? {},
    decompressionBand: pressure.value?.decompression_band ?? {},
    gammaFlipPoints,
    dexNeutral: dexNeutralLevel.value,
  }
})

function structureSnapshot(meta, spot) {
  if (!meta.rows.length || spot == null) {
    return {
      localBand: 1000,
      localGex: 0,
      dominantMagnet: null,
      gammaLevelBreakScore: 0,
      airPocketScore: 0,
      flipProximityScore: 0,
      upperWall: null,
      lowerWall: null,
      pinCenter: null,
      expansionComponents: {},
      pinningComponents: {},
      directionBias: 1,
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
  const insidePin = insideBand(spot, meta.pinningBand)
  const distanceInsideCluster = insidePin
    ? 72 + (28 * clamp(1 - ((pinDistance || 0) / Math.max((pinWidth || 1) / 2, 1)), 0, 1))
    : scoreDistance(distanceToBand(spot, meta.pinningBand) ?? (localBand * 1.6), localBand * 1.4)

  const localLongGammaScore = scoreRatio(Math.max(localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const localShortGammaScore = scoreRatio(Math.max(-localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const lowGammaScore = scoreInverseRatio(localAbsGex, Math.max(meta.totalAbsGex * 0.12, 1), 1.0)
  const oiConcentrationScore = scoreRatio(localOi, Math.max(meta.totalOi * 0.22, 1), 1.0)
  const strikeMagnetScore = dominantMagnet
    ? clamp(dominantMagnet.proximity * dominantMagnet.strength * 140, 0, 100)
    : 0

  const airPocketScore = clamp(
    (
      (1 - clamp(shellOi / Math.max(meta.totalOi * 0.22, 1), 0, 1)) * 0.55
      + (1 - clamp(shellAbsGex / Math.max(meta.totalAbsGex * 0.20, 1), 0, 1)) * 0.45
    ) * 100,
    0,
    100,
  )

  const flipDistance = nearestGammaFlipDistance(spot, meta.gammaFlipPoints)
  const flipProximityScore = flipDistance != null ? scoreDistance(flipDistance, localBand * 0.85) : 0
  const upperWall = bestWall(meta, spot, 1)
  const lowerWall = bestWall(meta, spot, -1)

  let gammaLevelBreakScore = 12
  if (insideBand(spot, meta.decompressionBand)) gammaLevelBreakScore = 86
  else if (insideBand(spot, meta.accelerationBand)) gammaLevelBreakScore = 72
  else if (!insidePin) gammaLevelBreakScore = 54
  gammaLevelBreakScore = clamp(gammaLevelBreakScore + (flipProximityScore * 0.16), 0, 100)

  const dexNeutralDistance = meta.dexNeutral != null ? Math.abs(meta.dexNeutral - spot) : null
  const dexNeutralScore = dexNeutralDistance != null ? scoreDistance(dexNeutralDistance, localBand * 1.0) : 0
  const directionBias = Math.sign((dominantMagnet?.strike ?? pinCenter ?? spot) - spot) || Math.sign(localGex) || 1

  return {
    localBand,
    localGex,
    dominantMagnet,
    upperWall,
    lowerWall,
    pinCenter,
    flipDistance,
    dexNeutralDistance,
    pinningComponents: {
      localLongGammaScore,
      oiConcentrationScore,
      strikeMagnetScore,
      distanceInsideCluster,
      dexNeutralScore,
    },
    expansionComponents: {
      shortGammaOrLowGammaScore: Math.max(localShortGammaScore, lowGammaScore),
      gammaLevelBreakScore,
      airPocketScore,
      flipProximityScore,
    },
    gammaLevelBreakScore,
    airPocketScore,
    flipProximityScore,
    directionBias,
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

function vegaScoreForEvent(item, fallbackSpot) {
  const explicitVega = safeNumber(item._vega)
  if (explicitVega != null && explicitVega > 0) return explicitVega * Math.max(item._volume || 1, 1)
  const eventSpot = item._spot || fallbackSpot
  const strike = item._strike || eventSpot || fallbackSpot
  const distPct = eventSpot > 0 ? Math.abs(strike - eventSpot) / eventSpot : 0
  const proxWeight = distPct <= 0.015 ? 1.15 : distPct <= 0.04 ? 1.0 : distPct <= 0.08 ? 0.72 : 0.42
  const atmness = 1 - clamp(Math.abs((item._delta || 0.5) - 0.5) / 0.5, 0, 1)
  const termWeight = item._days != null ? clamp(Math.sqrt(Math.max(item._days, 1) / 30), 0.65, 2.2) : 1.0
  return item._volume * proxWeight * termWeight * (0.45 + (0.55 * atmness))
}

function buildFlowWindowSnapshots(records, flow, fallbackSpot) {
  if (!records.length) return []
  const prepared = flow
    .filter(item => item._epoch != null && item._volume > 0)
    .map(item => ({
      epoch: item._epoch,
      side: item._side,
      score: flowScoreForEvent(item, fallbackSpot),
      vegaScore: vegaScoreForEvent(item, fallbackSpot),
    }))
    .filter(item => item.score > 0 || item.vegaScore > 0)
    .sort((left, right) => left.epoch - right.epoch)

  let start = 0
  let end = 0
  let callFlow = 0
  let putFlow = 0
  let callVega = 0
  let putVega = 0

  return records.map(record => {
    const currentEpoch = record?._epoch
    if (currentEpoch == null) {
      return {
        callFlow: 0,
        putFlow: 0,
        totalFlow: 0,
        flowImbalance: 0,
        directionalFlowScore: 0,
        callVega: 0,
        putVega: 0,
        totalVega: 0,
        vegaImbalance: 0,
      }
    }
    while (end < prepared.length && prepared[end].epoch <= currentEpoch) {
      if (prepared[end].side === 'P') {
        putFlow += prepared[end].score
        putVega += prepared[end].vegaScore
      } else {
        callFlow += prepared[end].score
        callVega += prepared[end].vegaScore
      }
      end += 1
    }
    const cutoffEpoch = currentEpoch - (30 * 60 * 1000)
    while (start < end && prepared[start].epoch < cutoffEpoch) {
      if (prepared[start].side === 'P') {
        putFlow -= prepared[start].score
        putVega -= prepared[start].vegaScore
      } else {
        callFlow -= prepared[start].score
        callVega -= prepared[start].vegaScore
      }
      start += 1
    }
    callFlow = Math.max(callFlow, 0)
    putFlow = Math.max(putFlow, 0)
    callVega = Math.max(callVega, 0)
    putVega = Math.max(putVega, 0)
    const totalFlow = callFlow + putFlow
    const totalVega = callVega + putVega
    const flowImbalance = totalFlow > 0 ? (callFlow - putFlow) / totalFlow : 0
    const vegaImbalance = totalVega > 0 ? (callVega - putVega) / totalVega : 0
    const directionalFlowScore = totalFlow > 0
      ? clamp(Math.abs(flowImbalance) * Math.sqrt(totalFlow / 2500) * 100, 0, 100)
      : 0
    return {
      callFlow,
      putFlow,
      totalFlow,
      flowImbalance,
      directionalFlowScore,
      callVega,
      putVega,
      totalVega,
      vegaImbalance,
    }
  })
}

function breakoutLevels(point, meta, forcedDirection = null) {
  const direction = forcedDirection == null
    ? (Math.abs(point.directionBias) > 0 ? point.directionBias : 1)
    : forcedDirection
  const accel = meta.accelerationBand || {}
  const pin = meta.pinningBand || {}
  const decomp = meta.decompressionBand || {}
  const dominantMagnet = point.structure?.dominantMagnet?.strike ?? bandCenter(pin) ?? point.structurePrice ?? point.spot

  let breakoutLevel = null
  if (direction > 0) breakoutLevel = safeNumber(accel.high ?? decomp.high ?? pin.high)
  else breakoutLevel = safeNumber(accel.low ?? decomp.low ?? pin.low)

  let returnLevel = dominantMagnet
  if (direction > 0 && safeNumber(pin.high) != null) returnLevel = safeNumber(pin.high)
  if (direction < 0 && safeNumber(pin.low) != null) returnLevel = safeNumber(pin.low)

  return {
    direction,
    breakoutLevel,
    returnLevel,
    confirmationText: direction > 0
      ? `acima de ${formatLevel(breakoutLevel)} ativa expansao compradora`
      : `abaixo de ${formatLevel(breakoutLevel)} ativa expansao vendedora`,
    invalidationText: direction > 0
      ? `volta abaixo de ${formatLevel(returnLevel)} esfria a ignicao`
      : `retorno acima de ${formatLevel(returnLevel)} esfria a ignicao`,
  }
}

function dominantTriggerLabel(components) {
  const sorted = components.slice().sort((left, right) => (right.score || 0) - (left.score || 0))
  const first = sorted[0]
  const second = sorted[1]
  if (!first) return '--'
  if (second && second.score >= Math.max(first.score - 6, 60)) return `${first.label} + ${second.label}`
  return first.label
}

function buildIgnitionPoint(records, index, surfacePack, meta, flowWindow, openPrice) {
  const record = records[index]
  const futurePrice = safeNumber(record?._future_price ?? record?._price)
  const spotDisplay = safeNumber(record?._spot_price ?? record?.spot ?? marketContext.value?.spot_price)
  const structurePrice = futurePrice ?? spotDisplay
  if (structurePrice == null) return null

  const structure = structureSnapshot(meta, structurePrice)
  const fifteenSlice = trailingRecords(records, index, 15)
  const thirtySlice = trailingRecords(records, index, 30)
  const prices15 = fifteenSlice.map(item => safeNumber(item?._future_price ?? item?._price ?? item?._spot_price)).filter(value => value != null)
  const prices30 = thirtySlice.map(item => safeNumber(item?._future_price ?? item?._price ?? item?._spot_price)).filter(value => value != null)
  const dayPrices = records.slice(0, index + 1).map(item => safeNumber(item?._future_price ?? item?._price ?? item?._spot_price)).filter(value => value != null)
  const priceHistoryAvailable = prices15.length >= 3 && prices30.length >= 6
  const trendEff15 = trendEfficiency(prices15)
  const trendEff30 = trendEfficiency(prices30)
  const latestPrice = prices15.length ? prices15[prices15.length - 1] : structurePrice
  const dayRange = dayPrices.length ? Math.max(...dayPrices) - Math.min(...dayPrices) : 0
  const sessionMeanPrice = mean(dayPrices) ?? latestPrice
  const open = openPrice ?? latestPrice

  const prev5 = nearestByMinutesAtIndex(records, index, 5)
  const prev15 = nearestByMinutesAtIndex(records, index, 15)
  const prev30 = nearestByMinutesAtIndex(records, index, 30)

  const ivCurrent = safeNumber(record.iv_atm)
  const rvCurrent = safeNumber(record.rv_garch_intraday ?? record.rv_live_3d ?? record.rv_live_5d)
  const ivPrev5 = safeNumber(prev5?.iv_atm)
  const ivPrev15 = safeNumber(prev15?.iv_atm)
  const ivDelta5mPts = ivCurrent != null && ivPrev5 != null ? (ivCurrent - ivPrev5) * 100 : 0
  const ivDelta15mPts = ivCurrent != null && ivPrev15 != null ? (ivCurrent - ivPrev15) * 100 : 0

  const skewCurrent = levelFor('skew', record)
  const skewPrev5 = levelFor('skew', prev5)
  const skewPrev15 = levelFor('skew', prev15)
  const skewDelta5m = skewCurrent != null && skewPrev5 != null ? (skewCurrent - skewPrev5) : 0
  const skewDelta15m = skewCurrent != null && skewPrev15 != null ? (skewCurrent - skewPrev15) : 0

  const putWingCurrent = levelFor('putWing', record)
  const putWingPrev5 = levelFor('putWing', prev5)
  const putWingPrev15 = levelFor('putWing', prev15)
  const putWingDelta5mPts = putWingCurrent != null && putWingPrev5 != null ? (putWingCurrent - putWingPrev5) * 100 : 0
  const putWingDelta15mPts = putWingCurrent != null && putWingPrev15 != null ? (putWingCurrent - putWingPrev15) * 100 : 0

  const callWingCurrent = levelFor('callWing', record)
  const callWingPrev5 = levelFor('callWing', prev5)
  const callWingPrev15 = levelFor('callWing', prev15)
  const callWingDelta5mPts = callWingCurrent != null && callWingPrev5 != null ? (callWingCurrent - callWingPrev5) * 100 : 0
  const callWingDelta15mPts = callWingCurrent != null && callWingPrev15 != null ? (callWingCurrent - callWingPrev15) * 100 : 0

  const ivLevels15 = fifteenSlice.map(item => safeNumber(item?.iv_atm)).filter(value => value != null)
  const rvLevels15 = fifteenSlice.map(item => safeNumber(item?.rv_garch_intraday ?? item?.rv_live_3d ?? item?.rv_live_5d)).filter(value => value != null)
  const skewLevels15 = fifteenSlice.map(item => levelFor('skew', item)).filter(value => value != null)
  const ivAcceleration = accelerationMetrics(ivLevels15, 'diff', 0.0009)
  const rvAcceleration = accelerationMetrics(rvLevels15, 'diff', 0.0009)
  const skewAcceleration = accelerationMetrics(skewLevels15, 'diff', 0.0007)

  const score5 = surfacePack.five.scoreSeries[index]?.score ?? null
  const score15 = surfacePack.fifteen.scoreSeries[index]?.score ?? null
  const surfaceMotionScore = (
    ((score5 ?? score15 ?? 0) * WINDOW_5.weight)
    + ((score15 ?? score5 ?? 0) * WINDOW_15.weight)
  ) / (WINDOW_5.weight + WINDOW_15.weight)

  const prevSurface15 = nearestByMinutesAtIndex(surfacePack.fifteenAligned, index, 15)
  const surfaceMotionDelta = surfaceMotionScore - (safeNumber(prevSurface15?.score) || 0)

  const flowImbalance = flowWindow?.flowImbalance || 0
  const directionalFlowScore = flowWindow?.directionalFlowScore || 0
  const totalFlow = flowWindow?.totalFlow || 0
  const totalVega = flowWindow?.totalVega || 0
  const vegaImbalance = flowWindow?.vegaImbalance || 0
  const totalOi = Math.max(meta.totalOi, 1)

  const totalVegaScore = scoreRatio(totalVega, Math.max(totalOi * 0.014, 1), 1.0)
  const directionalVegaScore = clamp(Math.abs(vegaImbalance) * 100, 0, 100)
  const vegaBuyingPressureScore = weightedScore([
    { score: totalVegaScore, weight: 0.68 },
    { score: directionalVegaScore, weight: 0.32 },
  ])

  const pinAnchor = structure.dominantMagnet?.strike ?? structure.pinCenter ?? latestPrice
  const spot5 = safeNumber(prev5?._future_price ?? prev5?._price ?? prev5?._spot_price) ?? open
  const spot15 = safeNumber(prev15?._future_price ?? prev15?._price ?? prev15?._spot_price) ?? open
  const spot30 = safeNumber(prev30?._future_price ?? prev30?._price ?? prev30?._spot_price) ?? open
  const move5 = latestPrice - spot5
  const move15 = latestPrice - spot15
  const move30 = latestPrice - spot30
  const directionalDistance = Math.abs(latestPrice - pinAnchor)
  const priceWindowMaxAnchorDist = prices30.length
    ? Math.max(...prices30.map(price => Math.abs(price - pinAnchor)))
    : directionalDistance
  const meanReversionScore = clamp((1 - trendEff15) * (1 - clamp(directionalDistance / Math.max(priceWindowMaxAnchorDist || structure.localBand, 1), 0, 1)) * 120, 0, 100)
  const rangeExtension = dayRange > 0 ? Math.abs(latestPrice - open) / dayRange : 0
  const futureAggressionScore = clamp(((trendEff30 * 0.62) + (clamp(directionalDistance / structure.localBand, 0, 1) * 0.23) + (clamp(rangeExtension, 0, 1) * 0.15)) * 100, 0, 100)
  const vwapProxyBreakScore = clamp((Math.abs(latestPrice - sessionMeanPrice) / Math.max(structure.localBand, 1)) * 100, 0, 100)
  const anchorEscapeScore = clamp((directionalDistance / Math.max(structure.localBand, 1)) * 100, 0, 100)

  const rvGap = ivCurrent != null && rvCurrent != null ? ivCurrent - rvCurrent : null
  const lowRealizedVolScore = rvGap != null
    ? clamp((clamp(rvGap / Math.max(ivCurrent * 0.35, 0.02), 0, 1) * 0.65 + (1 - trendEff15) * 0.35) * 100, 0, 100)
    : clamp((1 - trendEff15) * 70, 0, 100)
  const rvExpansionScore = rvGap != null
    ? clamp(((1 - clamp(rvGap / Math.max(ivCurrent * 0.25, 0.015), 0, 1)) * 0.45 + trendEff30 * 0.55) * 100, 0, 100)
    : clamp(trendEff30 * 70, 0, 100)

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

  const skewStressScore = clamp(Math.max(skewDelta15m * 100, 0) * 56, 0, 100)
  const putWingStressScore = clamp(Math.max(putWingDelta15mPts, 0) * 65, 0, 100)
  const callWingStressScore = clamp(Math.max(callWingDelta15mPts, 0) * 65, 0, 100)
  const microIvPulseScore = clamp(Math.max(ivDelta5mPts, 0) / 0.55 * 100, 0, 100)
  const microSkewPulseScore = clamp(Math.abs(skewDelta5m * 100) / 10.5 * 100, 0, 100)
  const microPutWingPulseScore = clamp(Math.max(putWingDelta5mPts, 0) / 1.10 * 100, 0, 100)
  const microCallWingPulseScore = clamp(Math.max(callWingDelta5mPts, 0) / 1.10 * 100, 0, 100)
  const microPricePulseScore = clamp(Math.abs(move5) / Math.max(structure.localBand * 0.38, 180), 0, 1) * 100
  const microPulseScore = weightedScore([
    { score: microIvPulseScore, weight: 0.30 },
    { score: Math.max(microSkewPulseScore, microPutWingPulseScore, microCallWingPulseScore), weight: 0.28 },
    { score: microPricePulseScore, weight: 0.22 },
    { score: clamp(Math.max(surfaceMotionDelta, 0) * 7.5, 0, 100), weight: 0.20 },
  ])
  const surfaceDistortionScore = weightedScore([
    { score: surfaceMotionScore, weight: 0.45 },
    { score: Math.max(skewStressScore, 0), weight: 0.18 },
    { score: putWingStressScore, weight: 0.22 },
    { score: callWingStressScore, weight: 0.15 },
  ])

  const callBiasScore = clamp(directionalFlowScore * Math.max(flowImbalance, 0), 0, 100)
  const putBiasScore = clamp(directionalFlowScore * Math.max(-flowImbalance, 0), 0, 100)
  const upMoveScore = clamp((move15 / structure.localBand) * 100, 0, 100)
  const downMoveScore = clamp((-move15 / structure.localBand) * 100, 0, 100)
  const move30Scores = signedDirectionalScore(move30, Math.max(structure.localBand * 1.4, 1))
  const futureUpConfirmationScore = weightedScore([
    { score: futureAggressionScore, weight: 0.58 },
    { score: move30Scores.up, weight: 0.26 },
    { score: upMoveScore, weight: 0.16 },
  ])
  const futureDownConfirmationScore = weightedScore([
    { score: futureAggressionScore, weight: 0.58 },
    { score: move30Scores.down, weight: 0.26 },
    { score: downMoveScore, weight: 0.16 },
  ])

  const pinningComponents = [
    { label: 'Local long gamma', score: structure.pinningComponents.localLongGammaScore || 0 },
    { label: 'OI perto do spot', score: structure.pinningComponents.oiConcentrationScore || 0 },
    { label: 'Strike magnet', score: structure.pinningComponents.strikeMagnetScore || 0 },
    { label: 'IV compression', score: ivCompressionScore },
    { label: 'Low realized vol', score: lowRealizedVolScore },
    { label: 'Mean reversion', score: meanReversionScore },
    { label: 'Dentro do cluster', score: structure.pinningComponents.distanceInsideCluster || 0 },
  ]
  const expansionComponents = [
    { label: 'Short/low gamma', score: structure.expansionComponents.shortGammaOrLowGammaScore || 0 },
    { label: 'IV expansion', score: ivExpansionScore },
    { label: 'Vol of vol rising', score: surfaceMotionScore },
    { label: 'Trend efficiency', score: clamp(trendEff30 * 100, 0, 100) },
    { label: 'Gamma level break', score: structure.gammaLevelBreakScore || 0 },
    { label: 'Directional flow', score: directionalFlowScore },
    { label: 'Future aggression', score: futureAggressionScore },
    { label: 'Air pocket', score: structure.airPocketScore || 0 },
  ]
  const pinningScore = mean(pinningComponents.map(item => item.score)) || 0
  const expansionScore = mean(expansionComponents.map(item => item.score)) || 0

  const dealerPainScore = weightedScore([
    { score: structure.gammaLevelBreakScore || 0, weight: 0.24 },
    { score: structure.airPocketScore || 0, weight: 0.16 },
    { score: structure.flipProximityScore || 0, weight: 0.12 },
    { score: structure.pinningComponents.dexNeutralScore || 0, weight: 0.08 },
    { score: surfaceDistortionScore, weight: 0.14 },
    { score: scoreRatio(Math.abs(safeNumber(meta.totals?.vex) || 0), Math.max(meta.totalAbsGex * 0.08, 1), 1.0), weight: 0.12 },
    { score: scoreRatio(Math.abs(safeNumber(meta.totals?.cex) || 0), Math.max(meta.totalAbsGex * 0.08, 1), 1.0), weight: 0.10 },
    { score: futureAggressionScore, weight: 0.04 },
  ])

  const gammaFragilityScore = weightedScore([
    { score: structure.expansionComponents.shortGammaOrLowGammaScore || 0, weight: 0.28 },
    { score: structure.gammaLevelBreakScore || 0, weight: 0.24 },
    { score: structure.airPocketScore || 0, weight: 0.18 },
    { score: structure.flipProximityScore || 0, weight: 0.16 },
    { score: clamp(100 - pinningScore, 0, 100), weight: 0.14 },
  ])

  const calibrationStart = Math.max(0, index - 150)
  const calibrationRecords = records.slice(calibrationStart, index + 1)
  const calibrationPriceLevels = calibrationRecords.map(item => safeNumber(item?._future_price ?? item?._price ?? item?._spot_price)).filter(value => value != null)
  const calibrationIvLevels = calibrationRecords.map(item => safeNumber(item?.iv_atm)).filter(value => value != null)
  const calibrationSkewLevels = calibrationRecords.map(item => levelFor('skew', item)).filter(value => value != null)
  const calibrationPutWingLevels = calibrationRecords.map(item => levelFor('putWing', item)).filter(value => value != null)
  const calibrationCallWingLevels = calibrationRecords.map(item => levelFor('callWing', item)).filter(value => value != null)
  const calibrationSurface15 = surfacePack.fifteen.scoreSeries.slice(calibrationStart, index + 1).map(item => safeNumber(item?.score)).filter(value => value != null)
  const calibrationIvDiff5Pts = buildLagDiffs(calibrationIvLevels, 5, 100)
  const calibrationIvDiff15Pts = buildLagDiffs(calibrationIvLevels, 15, 100)
  const calibrationSkewDiff5Pts = buildLagDiffs(calibrationSkewLevels, 5, 100)
  const calibrationSkewDiff15Pts = buildLagDiffs(calibrationSkewLevels, 15, 100)
  const calibrationPutWingDiff5Pts = buildLagDiffs(calibrationPutWingLevels, 5, 100)
  const calibrationPutWingDiff15Pts = buildLagDiffs(calibrationPutWingLevels, 15, 100)
  const calibrationCallWingDiff5Pts = buildLagDiffs(calibrationCallWingLevels, 5, 100)
  const calibrationCallWingDiff15Pts = buildLagDiffs(calibrationCallWingLevels, 15, 100)
  const calibrationPriceMove5 = buildLagDiffs(calibrationPriceLevels, 5, 1)
  const calibrationPriceMove15 = buildLagDiffs(calibrationPriceLevels, 15, 1)

  const adaptiveIvShockScore = weightedScore([
    { score: adaptiveShockScore(Math.max(ivDelta5mPts, ivDelta15mPts), calibrationIvDiff5Pts.concat(calibrationIvDiff15Pts), { positive: true, fallbackScale: 0.55 }), weight: 0.56 },
    { score: adaptiveShockScore(Math.max(ivAcceleration.current || 0, 0), calibrationIvDiff5Pts, { positive: true, fallbackScale: 0.35 }), weight: 0.44 },
  ])
  const adaptiveSkewShockScore = weightedScore([
    { score: adaptiveShockScore(skewDelta5m * 100, calibrationSkewDiff5Pts, { absolute: true, fallbackScale: 8 }), weight: 0.42 },
    { score: adaptiveShockScore(skewDelta15m * 100, calibrationSkewDiff15Pts, { absolute: true, fallbackScale: 10 }), weight: 0.58 },
  ])
  const adaptivePutWingShockScore = weightedScore([
    { score: adaptiveShockScore(putWingDelta5mPts, calibrationPutWingDiff5Pts, { positive: true, fallbackScale: 0.80 }), weight: 0.42 },
    { score: adaptiveShockScore(putWingDelta15mPts, calibrationPutWingDiff15Pts, { positive: true, fallbackScale: 1.05 }), weight: 0.58 },
  ])
  const adaptiveCallWingShockScore = weightedScore([
    { score: adaptiveShockScore(callWingDelta5mPts, calibrationCallWingDiff5Pts, { positive: true, fallbackScale: 0.80 }), weight: 0.42 },
    { score: adaptiveShockScore(callWingDelta15mPts, calibrationCallWingDiff15Pts, { positive: true, fallbackScale: 1.05 }), weight: 0.58 },
  ])
  const adaptiveSurfaceMotionScore = weightedScore([
    { score: adaptiveShockScore(surfaceMotionScore, calibrationSurface15, { positive: true, fallbackScale: 8 }), weight: 0.62 },
    { score: adaptiveShockScore(surfaceMotionDelta, buildLagDiffs(calibrationSurface15, 15, 1), { positive: true, fallbackScale: 6 }), weight: 0.38 },
  ])
  const calibrationRangeExtension = calibrationPriceMove15
    .map(value => Math.abs(value) / Math.max(dayRange || Math.abs(value), 1))
    .filter(value => Number.isFinite(value))
  const adaptivePriceImpulseScore = weightedScore([
    { score: adaptiveShockScore(move5, calibrationPriceMove5, { absolute: true, fallbackScale: Math.max(structure.localBand * 0.16, 120) }), weight: 0.34 },
    { score: adaptiveShockScore(move15, calibrationPriceMove15, { absolute: true, fallbackScale: Math.max(structure.localBand * 0.28, 220) }), weight: 0.44 },
    { score: adaptiveShockScore(rangeExtension, calibrationRangeExtension, { positive: true, fallbackScale: 0.12 }), weight: 0.22 },
  ])

  const skewExpansionBaseScore = weightedScore([
    { score: skewAcceleration.score, weight: 0.34 },
    { score: skewStressScore, weight: 0.24 },
    { score: putWingStressScore, weight: 0.26 },
    { score: callWingStressScore, weight: 0.16 },
  ])

  const realizedVolAccelerationBaseScore = weightedScore([
    { score: rvAcceleration.score, weight: 0.60 },
    { score: rvExpansionScore, weight: 0.40 },
  ])

  const breakoutConfirmationBaseScore = weightedScore([
    { score: structure.gammaLevelBreakScore || 0, weight: 0.34 },
    { score: vwapProxyBreakScore, weight: 0.18 },
    { score: anchorEscapeScore, weight: 0.16 },
    { score: clamp(rangeExtension * 100, 0, 100), weight: 0.14 },
    { score: clamp(trendEff30 * 100, 0, 100), weight: 0.18 },
  ])

  const futureDirectionBias = Math.abs(flowImbalance) > 0.08
    ? Math.sign(flowImbalance)
    : Math.abs(move30) > Math.abs(move15)
      ? Math.sign(move30)
      : Math.sign(move15) || structure.directionBias || 1
  const futureAggressionConfirmationBaseScore = futureDirectionBias >= 0 ? futureUpConfirmationScore : futureDownConfirmationScore

  const ivAccelerationBaseScore = weightedScore([
    { score: ivAcceleration.score, weight: 0.64 },
    { score: ivExpansionScore, weight: 0.36 },
  ])

  const ivAccelerationScore = blendScores(ivAccelerationBaseScore, adaptiveIvShockScore, 0.56)
  const skewExpansionScore = blendScores(skewExpansionBaseScore, adaptiveSkewShockScore, 0.54)
  const realizedVolAccelerationScore = blendScores(realizedVolAccelerationBaseScore, adaptivePriceImpulseScore, rvCurrent != null ? 0.34 : 0.46)
  const breakoutConfirmationScore = blendScores(breakoutConfirmationBaseScore, adaptivePriceImpulseScore, 0.40)
  const futureAggressionConfirmationScore = blendScores(futureAggressionConfirmationBaseScore, adaptivePriceImpulseScore, 0.30)

  const adaptiveWingStressScore = Math.max(adaptivePutWingShockScore, adaptiveCallWingShockScore)
  const surfaceShockScore = weightedScore([
    { score: ivAccelerationScore, weight: 0.23 },
    { score: blendScores(surfaceMotionScore, adaptiveSurfaceMotionScore, 0.48), weight: 0.20 },
    { score: skewExpansionScore, weight: 0.18 },
    { score: adaptiveWingStressScore, weight: 0.16 },
    { score: surfaceDistortionScore, weight: 0.13 },
    { score: microPulseScore, weight: 0.10 },
  ])
  const transmissionScore = weightedScore([
    { score: gammaFragilityScore, weight: 0.18 },
    { score: breakoutConfirmationScore, weight: 0.21 },
    { score: futureAggressionConfirmationScore, weight: 0.18 },
    { score: realizedVolAccelerationScore, weight: 0.14 },
    { score: adaptivePriceImpulseScore, weight: 0.15 },
    { score: directionalFlowScore, weight: 0.08 },
    { score: dealerPainScore, weight: 0.06 },
  ])
  const ignitionEvidenceCount = [
    ivAccelerationScore >= 52,
    surfaceShockScore >= 54,
    skewExpansionScore >= 48 || adaptiveWingStressScore >= 50,
    gammaFragilityScore >= 46 || breakoutConfirmationScore >= 48,
    futureAggressionConfirmationScore >= 46 || directionalFlowScore >= 42,
    microPulseScore >= 48 || adaptivePriceImpulseScore >= 50,
  ].filter(Boolean).length
  const ignitionEvidenceScore = clamp((ignitionEvidenceCount / 6) * 100, 0, 100)
  const surfaceIgnitionComposite = weightedScore([
    { score: surfaceShockScore, weight: 0.54 },
    { score: adaptiveSurfaceMotionScore, weight: 0.18 },
    { score: adaptiveWingStressScore, weight: 0.14 },
    { score: microPulseScore, weight: 0.14 },
  ])
  const confirmationProbability = weightedScore([
    { score: surfaceShockScore, weight: 0.42 },
    { score: transmissionScore, weight: 0.34 },
    { score: ignitionEvidenceScore, weight: 0.14 },
    { score: Math.max(microPulseScore, adaptivePriceImpulseScore), weight: 0.10 },
  ])
  const failedIgnitionRiskScore = weightedScore([
    { score: clamp(100 - transmissionScore, 0, 100), weight: 0.30 },
    { score: clamp(100 - futureAggressionConfirmationScore, 0, 100), weight: 0.20 },
    { score: clamp(100 - breakoutConfirmationScore, 0, 100), weight: 0.18 },
    { score: clamp(surfaceShockScore - transmissionScore, 0, 100), weight: 0.18 },
    { score: clamp(100 - realizedVolAccelerationScore, 0, 100), weight: 0.14 },
  ])
  const rawVolIgnitionScore = weightedScore([
    { score: surfaceShockScore, weight: 0.38 },
    { score: transmissionScore, weight: 0.26 },
    { score: confirmationProbability, weight: 0.20 },
    { score: vegaBuyingPressureScore, weight: 0.08 },
    { score: dealerPainScore, weight: 0.08 },
  ])
  const stretchedIgnitionScore = rawVolIgnitionScore >= 38
    ? Math.pow(rawVolIgnitionScore / 100, 0.80) * 100
    : rawVolIgnitionScore
  const ignitionBoost = clamp(
    Math.max(surfaceShockScore - 50, 0) * 0.20
    + Math.max(transmissionScore - 46, 0) * 0.18
    + Math.max(microPulseScore - 42, 0) * 0.18
    + Math.max(confirmationProbability - 50, 0) * 0.12
    + (ignitionEvidenceCount * 2.6),
    0,
    22,
  )
  const volIgnitionScore = clamp(
    stretchedIgnitionScore
    + ignitionBoost
    - (Math.max(failedIgnitionRiskScore - 78, 0) * 0.10),
    0,
    100,
  )

  const directionUpScore = weightedScore([
    { score: callBiasScore, weight: 0.28 },
    { score: callWingStressScore, weight: 0.20 },
    { score: upMoveScore, weight: 0.18 },
    { score: futureUpConfirmationScore, weight: 0.20 },
    { score: clamp(100 - skewStressScore, 0, 100), weight: 0.14 },
  ])
  const directionDownScore = weightedScore([
    { score: putBiasScore, weight: 0.28 },
    { score: skewStressScore, weight: 0.20 },
    { score: putWingStressScore, weight: 0.20 },
    { score: downMoveScore, weight: 0.16 },
    { score: futureDownConfirmationScore, weight: 0.16 },
  ])

  const twoSidedVolScore = weightedScore([
    { score: Math.min(putWingStressScore, callWingStressScore), weight: 0.42 },
    { score: surfaceDistortionScore, weight: 0.34 },
    { score: clamp(100 - directionalFlowScore, 0, 100), weight: 0.24 },
  ])

  const volOnlyScore = weightedScore([
    { score: surfaceMotionScore, weight: 0.34 },
    { score: vegaBuyingPressureScore, weight: 0.20 },
    { score: clamp(100 - directionalFlowScore, 0, 100), weight: 0.16 },
    { score: clamp(100 - Math.max(upMoveScore, downMoveScore), 0, 100), weight: 0.16 },
    { score: clamp(100 - Math.max(futureUpConfirmationScore, futureDownConfirmationScore), 0, 100), weight: 0.14 },
  ])

  const components = [
    { key: 'ivAcceleration', label: 'IV acceleration', score: ivAccelerationScore, tone: 'hot' },
    { key: 'volOfVol', label: 'Vol of vol z-score', score: surfaceMotionScore, tone: 'hot' },
    { key: 'microPulse', label: 'Micro pulse 5m', score: microPulseScore, tone: 'warm' },
    { key: 'vegaBuying', label: 'Vega buying pressure', score: vegaBuyingPressureScore, tone: 'warm' },
    { key: 'skewExpansion', label: 'Skew expansion', score: skewExpansionScore, tone: 'warn' },
    { key: 'rvAcceleration', label: 'Realized vol acceleration', score: realizedVolAccelerationScore, tone: 'hot' },
    { key: 'gammaFragility', label: 'Gamma fragility', score: gammaFragilityScore, tone: 'warn' },
    { key: 'breakout', label: 'Breakout confirmation', score: breakoutConfirmationScore, tone: 'warm' },
    { key: 'futureAggression', label: 'Future aggression confirmation', score: futureAggressionConfirmationScore, tone: 'hot' },
    { key: 'surfaceDistortion', label: 'Surface distortion', score: surfaceDistortionScore, tone: 'warn' },
  ]

  return {
    epoch: record._epoch,
    timestamp: record.captured_at,
    sessionDate: record._sessionDate,
    spot: spotDisplay ?? structurePrice,
    structurePrice,
    open,
    latestPrice,
    sessionMeanPrice,
    dayRange,
    ivAtm: ivCurrent,
    rvCurrent,
    ivDelta15mPts,
    skewDelta15m,
    putWingDelta15mPts,
    callWingDelta15mPts,
    ivAccelerationScore,
    ivAccelerationCurrent: ivAcceleration.current,
    ivAccelerationZ: ivAcceleration.z,
    surfaceMotionScore,
    surfaceMotionDelta,
    vegaBuyingPressureScore,
    totalVegaScore,
    directionalVegaScore,
    skewExpansionScore,
    realizedVolAccelerationScore,
    gammaFragilityScore,
    breakoutConfirmationScore,
    futureAggressionConfirmationScore,
    futureUpConfirmationScore,
    futureDownConfirmationScore,
    surfaceDistortionScore,
    surfaceShockScore,
    transmissionScore,
    confirmationProbability,
    failedIgnitionRiskScore,
    dealerPainScore,
    pinningScore,
    expansionScore,
    directionalFlowScore,
    flowImbalance,
    callBiasScore,
    putBiasScore,
    upMoveScore,
    downMoveScore,
    directionUpScore,
    directionDownScore,
    twoSidedVolScore,
    volOnlyScore,
    futureAggressionScore,
    ivCompressionScore,
    ivExpansionScore,
    rvExpansionScore,
    lowRealizedVolScore,
    skewStressScore,
    putWingStressScore,
    callWingStressScore,
    microPulseScore,
    surfaceIgnitionComposite,
    rawVolIgnitionScore,
    meanReversionScore,
    directionBias: futureDirectionBias === 0 ? (structure.directionBias || 1) : futureDirectionBias,
    priceHistoryAvailable,
    totalFlow,
    totalVega,
    structure,
    volIgnitionScore,
    components,
  }
}

function classifyDirection(point) {
  if ((point.twoSidedVolScore || 0) >= 66) return DIRECTION_META.two_sided
  if ((point.volOnlyScore || 0) >= 62 && Math.abs(point.flowImbalance || 0) < 0.15 && Math.max(point.upMoveScore || 0, point.downMoveScore || 0) < 48) {
    return DIRECTION_META.vol_only
  }
  if ((point.directionDownScore || 0) > (point.directionUpScore || 0) + 8) return DIRECTION_META.downside
  if ((point.directionUpScore || 0) > (point.directionDownScore || 0) + 8) return DIRECTION_META.upside
  return DIRECTION_META.vol_only
}

function classifyState(point, prevPoint, prev15Point, prevState = 'OFF') {
  const score = point?.volIgnitionScore || 0
  const delta15 = prev15Point ? score - (prev15Point.volIgnitionScore || 0) : 0
  const priceHistoryAvailable = point?.priceHistoryAvailable !== false
  const futureConfirmed = point?.futureAggressionConfirmationScore >= 55
  const breakoutConfirmed = point?.breakoutConfirmationScore >= 55
  const ivAlive = point?.ivAccelerationScore >= 50 || point?.ivExpansionScore >= 55
  const rvAlive = point?.realizedVolAccelerationScore >= 50
  const surfaceIgnitionComposite = safeNumber(point?.surfaceIgnitionComposite) ?? 0
  const surfaceShock = safeNumber(point?.surfaceShockScore) ?? surfaceIgnitionComposite
  const transmission = safeNumber(point?.transmissionScore) ?? weightedScore([
    { score: point?.gammaFragilityScore || 0, weight: 0.30 },
    { score: point?.breakoutConfirmationScore || 0, weight: 0.38 },
    { score: point?.futureAggressionConfirmationScore || 0, weight: 0.32 },
  ])
  const confirmation = safeNumber(point?.confirmationProbability) ?? weightedScore([
    { score: surfaceShock, weight: 0.56 },
    { score: transmission, weight: 0.44 },
  ])
  const failureRisk = safeNumber(point?.failedIgnitionRiskScore) ?? 0
  const stateJustRolled = prevPoint ? score < (prevPoint.volIgnitionScore || 0) - 5 : false
  if (!priceHistoryAvailable) {
    if (
      (confirmation >= 68 && surfaceShock >= 62 && delta15 >= -5)
      || (prevState === 'Expansion' && confirmation >= 63 && surfaceShock >= 58)
    ) return 'Expansion'
    if (
      (confirmation >= 56 && surfaceShock >= 52 && delta15 >= -7)
      || (prevState === 'Ignition' && confirmation >= 48 && surfaceShock >= 48)
    ) return 'Ignition'
    if (score >= 30 || surfaceShock >= 42 || surfaceIgnitionComposite >= 42) return 'Watch'
    return 'OFF'
  }
  if (
    (prevState === 'Expansion' || prevState === 'Ignition')
    && score >= 48
    && stateJustRolled
    && failureRisk >= 60
    && transmission < 46
    && (!ivAlive || !rvAlive)
  ) return 'Exhaustion'
  if (
    (confirmation >= 72 && transmission >= 56 && (futureConfirmed || breakoutConfirmed))
    || (prevState === 'Expansion' && confirmation >= 66 && transmission >= 50 && surfaceShock >= 56)
  ) return 'Expansion'
  if (
    (confirmation >= 56 && surfaceShock >= 52 && delta15 >= -5)
    || (surfaceShock >= 62 && transmission >= 44 && score >= 48)
    || (prevState === 'Ignition' && confirmation >= 50 && surfaceShock >= 48)
  ) return 'Ignition'
  if (score >= 32 || confirmation >= 40 || surfaceShock >= 42) return 'Watch'
  return 'OFF'
}

function classifySignal(point, prevPoint, prev15Point, prevState = 'OFF') {
  const score = point?.volIgnitionScore || 0
  const prevScore = prevPoint?.volIgnitionScore || 0
  const delta15 = prev15Point ? score - (prev15Point.volIgnitionScore || 0) : 0
  const priceHistoryAvailable = point?.priceHistoryAvailable !== false
  const surfaceAlive = point?.surfaceMotionScore >= 46 && point?.surfaceMotionDelta >= -6
  const ivAlive = point?.ivAccelerationScore >= 48 || point?.ivExpansionScore >= 52
  const skewAlive = point?.skewExpansionScore >= 44 || point?.surfaceDistortionScore >= 52
  const rvAlive = point?.realizedVolAccelerationScore >= 45
  const fragilityAlive = point?.gammaFragilityScore >= 45
  const breakoutAlive = point?.breakoutConfirmationScore >= 48
  const futureAlive = point?.futureAggressionConfirmationScore >= 46
  const vegaAlive = point?.vegaBuyingPressureScore >= 42
  const aliveCount = [surfaceAlive, ivAlive, skewAlive, rvAlive, fragilityAlive, breakoutAlive, futureAlive, vegaAlive].filter(Boolean).length
  const risingNow = score >= (prevScore - 1.5)
  const accelerationPulse = delta15 >= 2 || point?.surfaceMotionDelta >= 4 || point?.ivAccelerationCurrent > 0
  const directionConfirmed = breakoutAlive || futureAlive
  const reason = dominantTriggerLabel(point?.components || [])
  const surfaceIgnitionComposite = safeNumber(point?.surfaceIgnitionComposite) ?? 0
  const surfaceShock = safeNumber(point?.surfaceShockScore) ?? surfaceIgnitionComposite
  const transmission = safeNumber(point?.transmissionScore) ?? weightedScore([
    { score: point?.gammaFragilityScore || 0, weight: 0.28 },
    { score: point?.breakoutConfirmationScore || 0, weight: 0.36 },
    { score: point?.futureAggressionConfirmationScore || 0, weight: 0.36 },
  ])
  const confirmation = safeNumber(point?.confirmationProbability) ?? weightedScore([
    { score: surfaceShock, weight: 0.56 },
    { score: transmission, weight: 0.44 },
  ])
  const signalStrength = clamp(
    Math.max(score, confirmation)
    + (aliveCount * 4.5)
    + (directionConfirmed ? 7 : 0)
    + (accelerationPulse ? 5 : 0)
    + (fragilityAlive ? 4 : 0),
    0,
    100,
  )

  if (!priceHistoryAvailable) {
    if (
      (surfaceShock >= 66 && confirmation >= 60 && delta15 >= -3)
      || (surfaceIgnitionComposite >= 61 && score >= 48 && point?.ivAccelerationScore >= 58 && point?.skewExpansionScore >= 55)
    ) {
      return {
        rank: 3,
        kind: 'expansion',
        label: 'Expansion signal',
        reason,
        strength: clamp(signalStrength + 8, 0, 100),
      }
    }

    if (
      (surfaceShock >= 54 && confirmation >= 48 && delta15 >= -5)
      || (surfaceIgnitionComposite >= 52 && point?.ivAccelerationScore >= 54 && (point?.skewExpansionScore >= 50 || point?.putWingStressScore >= 52))
    ) {
      return {
        rank: 2,
        kind: 'ignition',
        label: 'Ignition signal',
        reason,
        strength: clamp(signalStrength + 6, 0, 100),
      }
    }

    if ((surfaceShock >= 42 || surfaceIgnitionComposite >= 44) && score >= 34 && (surfaceAlive || ivAlive || skewAlive)) {
      return {
        rank: 1,
        kind: 'watch',
        label: 'Watch pulse',
        reason,
        strength: clamp(signalStrength + 4, 0, 100),
      }
    }
  }

  if (
    (confirmation >= 72 && transmission >= 56 && aliveCount >= 4 && directionConfirmed && (fragilityAlive || skewAlive))
    || (score >= 64 && aliveCount >= 5 && breakoutAlive && futureAlive && risingNow)
  ) {
    return {
      rank: 3,
      kind: 'expansion',
      label: 'Expansion signal',
      reason,
      strength: signalStrength,
    }
  }

  if (
    (confirmation >= 56 && surfaceShock >= 52 && aliveCount >= 4 && risingNow)
    || (score >= 48 && aliveCount >= 5 && (directionConfirmed || fragilityAlive) && delta15 >= -4)
    || (score >= 45 && aliveCount >= 6 && accelerationPulse && (surfaceAlive || ivAlive))
    || (prevState === 'Expansion' && confirmation >= 50 && transmission >= 44)
  ) {
    return {
      rank: 2,
      kind: 'ignition',
      label: 'Ignition signal',
      reason,
      strength: signalStrength,
    }
  }

  if (
    score >= 34
    && aliveCount >= 3
    && delta15 >= -5
    && (surfaceAlive || ivAlive || skewAlive || surfaceShock >= 42)
  ) {
    return {
      rank: 1,
      kind: 'watch',
      label: 'Watch pulse',
      reason,
      strength: signalStrength,
    }
  }

  return {
    rank: 0,
    kind: 'off',
    label: 'No signal',
    reason,
    strength: signalStrength,
  }
}

function futureConfirmationLabel(score) {
  if (score >= 70) return 'forte'
  if (score >= 48) return 'parcial'
  return 'fraca'
}

function buildReading(point, state, directionMeta, levels) {
  const directionLabel = directionMeta.label
  if (state === 'OFF') {
    return `ha movimento na superficie, mas ainda sem transmissao limpa de vol para um processo de ignicao. ${directionLabel} segue mais como risco do que como fato.`
  }
  if (state === 'Watch') {
    return `o mercado esta mais instavel, mas ainda precisa de mais confirmacao de preco e futuro. ${levels.confirmationText} virou o gatilho mais importante.`
  }
  if (state === 'Ignition') {
    return `primeira fase de ignicao em andamento: IV, vol of vol e fragilidade de gamma ja sairam da compressao, mas a continuidade ainda depende de validacao estrutural.`
  }
  if (state === 'Expansion') {
    return `a ignicao ja entrou em modo expansion: superficie, realized e price action estao se reforcando e o risco de movimento reflexivo aumentou.`
  }
  return `o score segue alto, mas a aceleracao perdeu qualidade. o mercado parece mais perto de exaustao e compressao do que de uma nova perna limpa.`
}

function drawCenteredMessage(ctx, width, height, message) {
  ctx.save()
  ctx.fillStyle = '#6f8399'
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(message, width / 2, height / 2)
  ctx.restore()
}

const analytics = computed(() => {
  const records = sessionHistory.value
  const meta = structureMeta.value
  if (records.length < 8) return null

  const openPrice = safeNumber(records[0]?._future_price ?? records[0]?._price ?? records[0]?._spot_price)
  const surfacePack = {
    five: buildWindowScoreSeries(records, WINDOW_5, intradayMinuteHistory.value),
    fifteen: buildWindowScoreSeries(records, WINDOW_15, intradayMinuteHistory.value),
  }
  const fifteenAligned = surfacePack.fifteen.scoreSeries.map((item, innerIndex) => ({
    ...item,
    _epoch: records[innerIndex]?._epoch,
  }))
  const flowWindows = buildFlowWindowSnapshots(records, sessionFlow.value, openPrice)

  const historySeries = []
  const featureSeries = []
  for (let index = 0; index < records.length; index += 1) {
    const point = buildIgnitionPoint(records, index, { ...surfacePack, fifteenAligned }, meta, flowWindows[index], openPrice)
    if (!point) continue
    featureSeries.push(point)
  }

  if (!featureSeries.length) return null

  let previousDerivedState = 'OFF'
  for (let index = 0; index < featureSeries.length; index += 1) {
    const point = featureSeries[index]
    const prevPoint = index > 0 ? featureSeries[index - 1] : null
    const prev15Point = nearestByMinutesAtIndex(featureSeries, index, 15)
    const state = classifyState(point, prevPoint, prev15Point, previousDerivedState)
    const directionMeta = classifyDirection(point)
    const signalMeta = classifySignal(point, prevPoint, prev15Point, previousDerivedState)
    const stamp = new Date(point.epoch || 0)
    historySeries.push({
      epoch: point.epoch,
      timestamp: point.timestamp,
      sessionDate: point.sessionDate || latestSessionDate.value,
      score: point.volIgnitionScore,
      surfaceShockScore: point.surfaceShockScore,
      transmissionScore: point.transmissionScore,
      confirmationProbability: point.confirmationProbability,
      state,
      signalRank: signalMeta.rank,
      signalKind: signalMeta.kind,
      signalLabel: signalMeta.label,
      signalReason: signalMeta.reason,
      signalStrength: signalMeta.strength,
      directionKey: Object.keys(DIRECTION_META).find(key => DIRECTION_META[key].label === directionMeta.label) || 'vol_only',
      directionLabel: directionMeta.label,
      triggerLabel: dominantTriggerLabel(point.components),
      axisLabel: Number.isNaN(stamp.getTime())
        ? (latestSessionDate.value || 'today')
        : stamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    })
    previousDerivedState = state
  }

  const latestPoint = featureSeries[featureSeries.length - 1]
  const prev15Point = nearestByMinutes(featureSeries, 15)
  const scoreDelta15 = prev15Point ? latestPoint.volIgnitionScore - (prev15Point.volIgnitionScore || 0) : 0
  const latestHistoryPoint = historySeries[historySeries.length - 1] || null
  const state = latestHistoryPoint?.state || classifyState(latestPoint, featureSeries[featureSeries.length - 2] || null, prev15Point, historySeries[historySeries.length - 2]?.state || 'OFF')
  const stateMeta = STATE_META[state] || STATE_META.OFF
  const directionMeta = classifyDirection(latestPoint)
  const directionSign = directionMeta.label === 'Downside Ignition'
    ? -1
    : directionMeta.label === 'Upside Ignition'
      ? 1
      : latestPoint.directionBias
  const levels = breakoutLevels(latestPoint, meta, directionSign)
  const currentRecord = records[records.length - 1] || {}

  const principalTrigger = dominantTriggerLabel(latestPoint.components)
  const futureLabel = futureConfirmationLabel(latestPoint.futureAggressionConfirmationScore)
  const alerts = []
  const lastTwo = historySeries.slice(-2)

  if (lastTwo.length === 2 && lastTwo[0].score < 55 && lastTwo[1].score >= 55) alerts.push('Vol Ignition Watch')
  if (lastTwo.length === 2 && lastTwo[0].score < 70 && lastTwo[1].score >= 70) alerts.push('Vol Expansion Active')
  if (lastTwo.length === 2 && (lastTwo[0].signalRank || 0) < 2 && (lastTwo[1].signalRank || 0) >= 2) alerts.push('Ignition signal detectado')
  if (lastTwo.length === 2 && (lastTwo[0].signalRank || 0) < 3 && (lastTwo[1].signalRank || 0) >= 3) alerts.push('Expansion signal detectado')
  if (state !== 'OFF' && directionMeta.label === 'Downside Ignition' && latestPoint.futureDownConfirmationScore >= 58) alerts.push('Downside Ignition confirmado')
  if (state !== 'OFF' && directionMeta.label === 'Upside Ignition' && latestPoint.futureUpConfirmationScore >= 58) alerts.push('Upside Ignition confirmado')
  if (state !== 'OFF' && latestPoint.futureAggressionConfirmationScore < 50) alerts.push('Options-led but not futures-confirmed')
  if ((state === 'Ignition' || state === 'Expansion') && latestPoint.futureAggressionConfirmationScore >= 62) alerts.push('Reflexive Move Risk')

  const checklist = [
    {
      key: 'ivAcceleration',
      label: 'IV acelerando',
      active: latestPoint.ivAccelerationScore >= 55,
      partial: latestPoint.ivAccelerationScore >= 40,
      tone: latestPoint.ivAccelerationScore >= 55 ? 'on' : latestPoint.ivAccelerationScore >= 40 ? 'mid' : 'off',
      note: `${formatScore(latestPoint.ivAccelerationScore)}/100`,
    },
    {
      key: 'volOfVol',
      label: 'Vol of vol subindo',
      active: latestPoint.surfaceMotionScore >= 55 && latestPoint.surfaceMotionDelta > 0,
      partial: latestPoint.surfaceMotionScore >= 45,
      tone: latestPoint.surfaceMotionScore >= 55 && latestPoint.surfaceMotionDelta > 0 ? 'on' : latestPoint.surfaceMotionScore >= 45 ? 'mid' : 'off',
      note: `${formatScore(latestPoint.surfaceMotionScore)}/100`,
    },
    {
      key: 'skewExpansion',
      label: 'Skew/asa abrindo',
      active: latestPoint.skewExpansionScore >= 55,
      partial: latestPoint.skewExpansionScore >= 42,
      tone: latestPoint.skewExpansionScore >= 55 ? 'on' : latestPoint.skewExpansionScore >= 42 ? 'mid' : 'off',
      note: `${formatScore(latestPoint.skewExpansionScore)}/100`,
    },
    {
      key: 'vega',
      label: 'Vega comprada',
      active: latestPoint.vegaBuyingPressureScore >= 55,
      partial: latestPoint.vegaBuyingPressureScore >= 42,
      tone: latestPoint.vegaBuyingPressureScore >= 55 ? 'on' : latestPoint.vegaBuyingPressureScore >= 42 ? 'mid' : 'off',
      note: `${formatScore(latestPoint.vegaBuyingPressureScore)}/100`,
    },
    {
      key: 'future',
      label: 'Futuro confirmou',
      active: latestPoint.futureAggressionConfirmationScore >= 60,
      partial: latestPoint.futureAggressionConfirmationScore >= 45,
      tone: latestPoint.futureAggressionConfirmationScore >= 60 ? 'on' : latestPoint.futureAggressionConfirmationScore >= 45 ? 'mid' : 'off',
      note: futureLabel,
    },
    {
      key: 'gammaBreak',
      label: 'Preco perto de gamma cliff/break',
      active: latestPoint.gammaFragilityScore >= 55 || latestPoint.breakoutConfirmationScore >= 55,
      partial: latestPoint.gammaFragilityScore >= 40 || latestPoint.breakoutConfirmationScore >= 40,
      tone: latestPoint.gammaFragilityScore >= 55 || latestPoint.breakoutConfirmationScore >= 55 ? 'on' : latestPoint.gammaFragilityScore >= 40 || latestPoint.breakoutConfirmationScore >= 40 ? 'mid' : 'off',
      note: `${formatScore(Math.max(latestPoint.gammaFragilityScore, latestPoint.breakoutConfirmationScore))}/100`,
    },
  ]

  return {
    score: latestPoint.volIgnitionScore,
    scoreDelta15,
    state,
    stateTone: stateMeta.tone,
    stateColor: stateMeta.color,
    direction: directionMeta.label,
    directionTone: directionMeta.tone,
    principalTrigger,
    futureConfirmationLabel: futureLabel,
    confirmationText: levels.confirmationText,
    invalidationText: levels.invalidationText,
    reading: buildReading(latestPoint, state, directionMeta, levels),
    sessionStamp: sessionStampText(currentRecord),
    marketLabel: state === 'Expansion' ? 'mercado em fase reflexiva' : state === 'Ignition' ? 'primeira fase de expansao de vol' : state === 'Watch' ? 'compressao ficando fragil' : state === 'Exhaustion' ? 'ignicao cansando' : 'vol ainda sem ignicao clara',
    ivAtm: latestPoint.ivAtm,
    ivDelta15mPts: latestPoint.ivDelta15mPts,
    surfaceMotionScore: latestPoint.surfaceMotionScore,
    surfaceMotionDelta: latestPoint.surfaceMotionDelta,
    realizedVolAccelerationScore: latestPoint.realizedVolAccelerationScore,
    gammaFragilityScore: latestPoint.gammaFragilityScore,
    expansionScore: latestPoint.expansionScore,
    pinningScore: latestPoint.pinningScore,
    dealerPainScore: latestPoint.dealerPainScore,
    futureAggressionConfirmationScore: latestPoint.futureAggressionConfirmationScore,
    rvLabel: latestPoint.rvCurrent != null ? `RV ${pct(latestPoint.rvCurrent)}` : 'sem RV suficiente',
    gammaLabel: latestPoint.structure?.gammaLevelBreakScore >= 65 ? 'break estrutural ativo' : latestPoint.structure?.airPocketScore >= 55 ? 'air pocket por perto' : 'fragilidade moderada',
    pinExpLabel: latestPoint.expansionScore > latestPoint.pinningScore ? 'expansion domina' : latestPoint.pinningScore > latestPoint.expansionScore ? 'pinning ainda segura' : 'equilibrado',
    dealerLabel: latestPoint.dealerPainScore >= 70 ? 'zona sensivel' : latestPoint.dealerPainScore >= 50 ? 'stress moderado' : 'baixo stress',
    structureLabel: latestPoint.structure?.dominantMagnet?.strike != null ? `magneto ${formatLevel(latestPoint.structure.dominantMagnet.strike)}` : 'sem magneto claro',
    checklist,
    components: latestPoint.components,
    alerts,
    spot: latestPoint.spot,
    historySeries,
  }
})

const snapshot = computed(() => analytics.value)
const historySeries = computed(() => snapshot.value?.historySeries || [])
const historyHoverPoint = computed(() => {
  const index = historyHoverIndex.value
  if (index == null) return null
  return historySeries.value[index] || null
})
const displayHistoryPoint = computed(() => historyHoverPoint.value || historySeries.value[historySeries.value.length - 1] || null)

const historyLabel = computed(() => {
  const sessionDate = latestSessionDate.value
  const count = historySeries.value.length
  if (!sessionDate) return '1m / sem base'
  return `${sessionDate} / 1m / ${count} pts`
})

const gaugeStyle = computed(() => {
  const score = snapshot.value?.score || 0
  const color = snapshot.value?.stateColor || '#64748b'
  return {
    background: `conic-gradient(${color} 0deg ${(clamp(score, 0, 100) / 100) * 360}deg, rgba(148,163,184,0.14) ${(clamp(score, 0, 100) / 100) * 360}deg 360deg)`,
  }
})

function deltaTone(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return ''
  if (numeric > 0) return 'hot'
  if (numeric < 0) return 'cool'
  return ''
}

function drawHistoryChart() {
  const canvas = historyCanvas.value
  const host = canvas?.parentElement || historyWrap.value
  const data = historySeries.value
  if (!canvas || !host) return

  const width = Math.max(host.clientWidth || 0, 320)
  const height = Math.max(host.clientHeight || 0, HISTORY_HEIGHT)
  const dpr = window.devicePixelRatio || 1

  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0b1624'
  ctx.fillRect(0, 0, width, height)

  if (data.length < 2) {
    historyMetrics.value = null
    drawCenteredMessage(ctx, width, height, 'Waiting for 1m ignition history')
    return
  }

  const chartWidth = width - HISTORY_PAD.left - HISTORY_PAD.right
  const chartHeight = height - HISTORY_PAD.top - HISTORY_PAD.bottom
  const xOf = index => HISTORY_PAD.left + (index / Math.max(data.length - 1, 1)) * chartWidth
  const yOf = value => HISTORY_PAD.top + (1 - (clamp(value, 0, 100) / 100)) * chartHeight
  const xPositions = data.map((_, index) => xOf(index))
  historyMetrics.value = {
    width,
    height,
    plotX: HISTORY_PAD.left,
    plotY: HISTORY_PAD.top,
    plotW: chartWidth,
    plotH: chartHeight,
    xPositions,
  }

  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.10)'
  ctx.fillStyle = '#607d8b'
  ctx.lineWidth = 1
  ctx.font = '9px monospace'
  ;[0, 20, 35, 55, 70, 85, 100].forEach(tick => {
    const y = yOf(tick)
    ctx.beginPath()
    ctx.moveTo(HISTORY_PAD.left, y)
    ctx.lineTo(width - HISTORY_PAD.right, y)
    ctx.stroke()
    ctx.fillText(String(tick), 6, y + 3)
  })
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = 'rgba(251,191,36,0.28)'
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  ctx.moveTo(HISTORY_PAD.left, yOf(55))
  ctx.lineTo(width - HISTORY_PAD.right, yOf(55))
  ctx.stroke()
  ctx.strokeStyle = 'rgba(239,68,68,0.28)'
  ctx.beginPath()
  ctx.moveTo(HISTORY_PAD.left, yOf(70))
  ctx.lineTo(width - HISTORY_PAD.right, yOf(70))
  ctx.stroke()
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.14)'
  ctx.fillStyle = '#64748b'
  ctx.font = '8px monospace'
  const labelStep = Math.max(1, Math.floor(data.length / 8))
  data.forEach((point, index) => {
    if (index % labelStep !== 0 && index !== data.length - 1) return
    const x = xOf(index)
    ctx.fillText(point.axisLabel, x - 12, height - 8)
  })
  ctx.restore()

  const drawHistoryLine = (key, color, widthPx = 1.2, alpha = 0.85) => {
    ctx.save()
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.lineWidth = widthPx
    ctx.strokeStyle = color
    ctx.globalAlpha = alpha
    ctx.beginPath()
    let started = false
    data.forEach((point, index) => {
      const value = safeNumber(point?.[key])
      if (value == null) return
      const x = xPositions[index]
      const y = yOf(value)
      if (!started) {
        ctx.moveTo(x, y)
        started = true
      } else {
        ctx.lineTo(x, y)
      }
    })
    if (started) ctx.stroke()
    ctx.restore()
  }

  drawHistoryLine('surfaceShockScore', '#38bdf8', 1.15, 0.82)
  drawHistoryLine('transmissionScore', '#a3e635', 1.15, 0.78)

  ctx.save()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.lineWidth = 2
  ctx.strokeStyle = '#f5f7fa'
  ctx.beginPath()
  data.forEach((point, index) => {
    const x = xPositions[index]
    const y = yOf(point.score)
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.stroke()
  ctx.restore()

  const isSignalPeak = (index, minRank = 1) => {
    const current = data[index]
    if (!current || (current.signalRank || 0) < minRank) return false
    const currentStrength = current.signalStrength ?? current.score
    const prevStrength = (data[index - 1]?.signalRank || 0) >= minRank
      ? (data[index - 1]?.signalStrength ?? data[index - 1]?.score ?? -Infinity)
      : -Infinity
    const nextStrength = (data[index + 1]?.signalRank || 0) >= minRank
      ? (data[index + 1]?.signalStrength ?? data[index + 1]?.score ?? -Infinity)
      : -Infinity
    return currentStrength >= prevStrength && currentStrength >= nextStrength
  }

  const lastSignalMarkerByRank = { 1: null, 2: null, 3: null }
  const rememberSignalMarker = (rank, index) => {
    if (rank >= 1) lastSignalMarkerByRank[rank] = index
  }
  const canPlotSignalMarker = (rank, index, gap) => {
    const lastIndex = lastSignalMarkerByRank[rank]
    return lastIndex == null || (index - lastIndex) >= gap
  }

  const drawMarker = (x, y, kind) => {
    ctx.save()
    if (kind === 'watchPulse') {
      ctx.fillStyle = '#facc15'
      ctx.strokeStyle = 'rgba(250, 204, 21, 0.30)'
      ctx.lineWidth = 4
      ctx.beginPath()
      ctx.arc(x, y, 4.9, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fill()
      ctx.fillStyle = '#fffbea'
      ctx.beginPath()
      ctx.arc(x, y, 1.8, 0, Math.PI * 2)
      ctx.fill()
    } else if (kind === 'confirmIgnition') {
      ctx.fillStyle = '#fb923c'
      ctx.strokeStyle = 'rgba(251, 146, 60, 0.30)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.arc(x, y, 6.4, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fill()
      ctx.fillStyle = '#fff7ed'
      ctx.beginPath()
      ctx.arc(x, y, 2.3, 0, Math.PI * 2)
      ctx.fill()
    } else if (kind === 'confirmExpansion') {
      ctx.fillStyle = '#ef4444'
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.28)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.moveTo(x, y - 7)
      ctx.lineTo(x + 7, y)
      ctx.lineTo(x, y + 7)
      ctx.lineTo(x - 7, y)
      ctx.closePath()
      ctx.stroke()
      ctx.fill()
      ctx.fillStyle = '#fff5f5'
      ctx.beginPath()
      ctx.arc(x, y, 2.1, 0, Math.PI * 2)
      ctx.fill()
    } else if (kind === 'up55') {
      ctx.fillStyle = '#fbbf24'
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.30)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.arc(x, y, 5.6, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fill()
    } else if (kind === 'up70') {
      ctx.fillStyle = '#ef4444'
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.28)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.moveTo(x, y - 6)
      ctx.lineTo(x + 5.4, y + 5.4)
      ctx.lineTo(x - 5.4, y + 5.4)
      ctx.closePath()
      ctx.stroke()
      ctx.fill()
    } else if (kind === 'down55') {
      ctx.fillStyle = '#7dd3fc'
      ctx.strokeStyle = 'rgba(125, 211, 252, 0.28)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.rect(x - 4.2, y - 4.2, 8.4, 8.4)
      ctx.stroke()
      ctx.fill()
    } else if (kind === 'down70') {
      ctx.fillStyle = '#c084fc'
      ctx.strokeStyle = 'rgba(192, 132, 252, 0.28)'
      ctx.lineWidth = 5
      ctx.beginPath()
      ctx.moveTo(x, y + 6)
      ctx.lineTo(x + 5.4, y - 5.4)
      ctx.lineTo(x - 5.4, y - 5.4)
      ctx.closePath()
      ctx.stroke()
      ctx.fill()
    }
    ctx.restore()
  }

  const firstPoint = data[0]
  if ((firstPoint?.signalRank || 0) >= 3) {
    drawMarker(xPositions[0], yOf(firstPoint.score), 'confirmExpansion')
    rememberSignalMarker(3, 0)
  } else if ((firstPoint?.signalRank || 0) >= 2) {
    drawMarker(xPositions[0], yOf(firstPoint.score), 'confirmIgnition')
    rememberSignalMarker(2, 0)
  } else if ((firstPoint?.signalRank || 0) >= 1) {
    drawMarker(xPositions[0], yOf(firstPoint.score), 'watchPulse')
    rememberSignalMarker(1, 0)
  }

  for (let index = 1; index < data.length; index += 1) {
    const prev = data[index - 1]
    const current = data[index]
    const x = xPositions[index]
    const y = yOf(current.score)
    const prevSignalRank = prev.signalRank || 0
    const currentSignalRank = current.signalRank || 0
    const ignitionPeak = isSignalPeak(index, 2)
    const expansionPeak = isSignalPeak(index, 3)
    const watchPeak = isSignalPeak(index, 1)

    if (
      currentSignalRank >= 3
      && (
        prevSignalRank < 3
        || (expansionPeak && canPlotSignalMarker(3, index, 10))
      )
    ) {
      drawMarker(x, y, 'confirmExpansion')
      rememberSignalMarker(3, index)
    } else if (
      currentSignalRank >= 2
      && (
        prevSignalRank < 2
        || (ignitionPeak && canPlotSignalMarker(2, index, 14))
      )
    ) {
      drawMarker(x, y, 'confirmIgnition')
      rememberSignalMarker(2, index)
    } else if (
      currentSignalRank >= 1
      && (
        prevSignalRank < 1
        || (watchPeak && canPlotSignalMarker(1, index, 12) && current.score >= 42)
      )
    ) {
      drawMarker(x, y, 'watchPulse')
      rememberSignalMarker(1, index)
    }

    if (prev.score < 55 && current.score >= 55) {
      drawMarker(x, y, 'up55')
    }
    if (prev.score < 70 && current.score >= 70) {
      drawMarker(x, y, 'up70')
    }
    if (prev.score >= 55 && current.score < 55) {
      drawMarker(x, y, 'down55')
    }
    if (prev.score >= 70 && current.score < 70) {
      drawMarker(x, y, 'down70')
    }
  }

  const last = data[data.length - 1]
  ctx.save()
  ctx.fillStyle = snapshot.value?.stateColor || '#fb923c'
  ctx.beginPath()
  ctx.arc(xPositions[data.length - 1], yOf(last.score), 3.1, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()

  const hoverIndex = historyHoverIndex.value
  if (hoverIndex != null && data[hoverIndex]) {
    const hoverPoint = data[hoverIndex]
    const hoverX = xPositions[hoverIndex]
    const hoverY = yOf(hoverPoint.score)
    ctx.save()
    ctx.strokeStyle = 'rgba(255,255,255,0.22)'
    ctx.setLineDash([3, 4])
    ctx.beginPath()
    ctx.moveTo(hoverX, HISTORY_PAD.top)
    ctx.lineTo(hoverX, height - HISTORY_PAD.bottom)
    ctx.stroke()
    ctx.restore()

    ctx.save()
    ctx.fillStyle = '#f8fafc'
    ctx.beginPath()
    ctx.arc(hoverX, hoverY, 3.6, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    const hoverSurface = safeNumber(hoverPoint.surfaceShockScore)
    const hoverTransmission = safeNumber(hoverPoint.transmissionScore)
    if (hoverSurface != null) {
      ctx.save()
      ctx.fillStyle = '#38bdf8'
      ctx.beginPath()
      ctx.arc(hoverX, yOf(hoverSurface), 3, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }
    if (hoverTransmission != null) {
      ctx.save()
      ctx.fillStyle = '#a3e635'
      ctx.beginPath()
      ctx.arc(hoverX, yOf(hoverTransmission), 3, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }
  }
}

function updateHistoryHover(clientX) {
  const canvas = historyCanvas.value
  const metrics = historyMetrics.value
  const data = historySeries.value
  if (!canvas || !metrics || data.length <= 1) return
  const rect = canvas.getBoundingClientRect()
  const localX = clientX - rect.left
  const rawIndex = Math.round(((localX - metrics.plotX) / Math.max(metrics.plotW, 1)) * (data.length - 1))
  historyHoverIndex.value = clamp(rawIndex, 0, data.length - 1)
}

function handleHistoryEnter(event) {
  updateHistoryHover(event.clientX)
}

function handleHistoryMove(event) {
  updateHistoryHover(event.clientX)
}

function handleHistoryLeave() {
  historyHoverIndex.value = null
}

async function loadWorkbookPriceHistory({ underlyingSecurity, sessionDate } = {}) {
  const resolvedSessionDate = String(sessionDate || '').trim()
  if (!resolvedSessionDate) return

  const cachedFuture = readCache('future', underlyingSecurity)
  const cachedSpot = readCache('spot', underlyingSecurity)
  const memoryFutureRows = cachedWorkbookRowsForSession(futurePriceHistory.value, resolvedSessionDate)
  const memorySpotRows = cachedWorkbookRowsForSession(spotPriceHistory.value, resolvedSessionDate)
  const cachedFutureRows = cachedWorkbookRowsForSession(cachedFuture, resolvedSessionDate)
  const cachedSpotRows = cachedWorkbookRowsForSession(cachedSpot, resolvedSessionDate)
  const coldFutureRows = cachedFutureRows.length ? cachedFutureRows : memoryFutureRows
  const coldSpotRows = cachedSpotRows.length ? cachedSpotRows : memorySpotRows

  if (coldFutureRows.length && coldSpotRows.length) {
    futurePriceHistory.value = coldFutureRows.map(normalizeWorkbookSeriesRecord)
    spotPriceHistory.value = coldSpotRows.map(normalizeWorkbookSeriesRecord)
    try {
      const latestResponse = await withLocalTimeout(
        getLiveCaptureWorkbookLatest({
          underlying_security: underlyingSecurity,
          securities: [FUTURE_SECURITY, SPOT_SECURITY].join(','),
          session_date: resolvedSessionDate,
        }),
        'workbook latest',
        5_000,
      )
      const latestBySecurity = latestResponse?.data?.latest_by_security || {}
      const nextFutureRows = mergeWorkbookRows(coldFutureRows, latestBySecurity[FUTURE_SECURITY])
      const nextSpotRows = mergeWorkbookRows(coldSpotRows, latestBySecurity[SPOT_SECURITY])
      futurePriceHistory.value = nextFutureRows.map(normalizeWorkbookSeriesRecord)
      spotPriceHistory.value = nextSpotRows.map(normalizeWorkbookSeriesRecord)
      writeCache('future', underlyingSecurity, nextFutureRows)
      writeCache('spot', underlyingSecurity, nextSpotRows)
    } catch {
      // Cached cold history is enough for the chart; latest will retry on the next refresh.
    }
    return
  }

  const workbookResponse = await Promise.allSettled([
    withLocalTimeout(
      getLiveCaptureWorkbookSeries({
        underlying_security: underlyingSecurity,
        securities: [FUTURE_SECURITY, SPOT_SECURITY].join(','),
        session_date: resolvedSessionDate,
        session_count: 1,
        include_recent_state: true,
      }),
      'workbook price series',
      10_000,
    ),
  ])

  if (workbookResponse[0]?.status === 'fulfilled') {
    const payload = workbookResponse[0].value?.data || {}
    const rowsBySecurity = payload.series_by_security || {}
    const rows = rowsBySecurity[FUTURE_SECURITY] || []
    futurePriceHistory.value = rows.map(normalizeWorkbookSeriesRecord)
    if (rows.length) writeCache('future', underlyingSecurity, rows)
  } else if (cachedFuture) {
    futurePriceHistory.value = (cachedFutureRows.length ? cachedFutureRows : []).map(normalizeWorkbookSeriesRecord)
  }

  if (workbookResponse[0]?.status === 'fulfilled') {
    const payload = workbookResponse[0].value?.data || {}
    const rowsBySecurity = payload.series_by_security || {}
    const rows = rowsBySecurity[SPOT_SECURITY] || []
    spotPriceHistory.value = rows.map(normalizeWorkbookSeriesRecord)
    if (rows.length) writeCache('spot', underlyingSecurity, rows)
  } else if (cachedSpot) {
    spotPriceHistory.value = (cachedSpotRows.length ? cachedSpotRows : []).map(normalizeWorkbookSeriesRecord)
  }
}

async function load({ force = false } = {}) {
  const now = Date.now()
  if (!force && now - lastLoadAt < MIN_FETCH_INTERVAL_MS) return
  loading.value = true
  error.value = null
  try {
    let hasAnyData = false
    const cachedVol = readCache('vol', underlying.value) || readVolOfVolCache(underlying.value)
    const cachedFlow = readCache('flow', underlying.value)

    try {
      const volResponse = await withLocalTimeout(
        getVolIndexHistory({
          underlying: underlying.value,
          days: 10,
          intraday_days: 1,
        }),
        'vol history',
      )
      const payload = volResponse?.data || {}
      const nextDaily = (payload.daily_history || payload.history || []).map(normalizeVolRecord)
      const nextIntraday = (payload.intraday_history || []).map(normalizeVolRecord)
      if (nextDaily.length || nextIntraday.length) {
        dailyHistory.value = nextDaily
        intradayHistory.value = nextIntraday
        writeCache('vol', underlying.value, {
          daily_history: payload.daily_history || payload.history || [],
          intraday_history: payload.intraday_history || [],
        })
        hasAnyData = true
      }
    } catch {
      let fallbackVol = cachedVol
      if (!fallbackVol) {
        await delay(1800)
        fallbackVol = readCache('vol', underlying.value) || readVolOfVolCache(underlying.value)
      }
      if (fallbackVol) {
        dailyHistory.value = (fallbackVol.daily_history || []).map(normalizeVolRecord)
        intradayHistory.value = (fallbackVol.intraday_history || []).map(normalizeVolRecord)
        hasAnyData = dailyHistory.value.length > 0 || intradayHistory.value.length > 0
      }
    }

    try {
      const flowResponse = await withLocalTimeout(
        getVolumeActivity({
          underlying_security: underlying.value,
          limit: 900,
          lookback_days: 1,
        }),
        'volume activity',
        10_000,
      )
      const payload = flowResponse?.data
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : []
      flowEvents.value = rows.map(normalizeFlowEvent)
      if (rows.length) {
        writeCache('flow', underlying.value, rows)
        hasAnyData = true
      }
    } catch {
      if (cachedFlow) {
        flowEvents.value = (Array.isArray(cachedFlow) ? cachedFlow : []).map(normalizeFlowEvent)
        hasAnyData = hasAnyData || flowEvents.value.length > 0
      }
    }

    const resolvedSessionDate = intradayHistory.value[intradayHistory.value.length - 1]?._sessionDate
    if (resolvedSessionDate) {
      await loadWorkbookPriceHistory({
        underlyingSecurity: underlying.value,
        sessionDate: resolvedSessionDate,
      })
    }

    if (!hasAnyData && !intradayHistory.value.length && !flowEvents.value.length) {
      throw new Error('Failed to load ignition detector data')
    }

    lastLoadAt = Date.now()
    await nextTick()
    drawHistoryChart()
  } catch (err) {
    error.value = err?.response?.data?.error || err?.message || 'Failed to load ignition detector data'
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
  await load()
})

watch(historySeries, async () => {
  await nextTick()
  drawHistoryChart()
})

onMounted(async () => {
  await load({ force: true })
  refreshTimer = setInterval(() => load(), AUTO_REFRESH_MS)
  resizeHandler = () => drawHistoryChart()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
</script>


<style scoped src="./VolatilityIgnitionDetectorWidget.css"></style>
