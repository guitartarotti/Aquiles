<template>
  <div class="apc-root">
    <div class="apc-toolbar">
      <span class="apc-badge">10p</span>
      <span class="apc-pill">XB1 {{ formatPrice(latestRow?.close) }}</span>
      <span class="apc-pill">MA271 {{ formatPrice(latestRow?.ma_271) }}</span>
      <span class="apc-pill vol">ATM IV {{ formatPct(resolvedAtmIv) }}</span>
      <span class="apc-pill" v-if="latestRow && latestRow.complete === false">parcial</span>
      <div class="apc-spacer" />
      <button class="apc-btn" @click="reload({ forceRefresh: true })">Atualizar</button>
      <span class="apc-meta" v-if="payload?.chart_rows?.length">{{ payload.chart_rows.length }} candles</span>
      <span class="apc-loading" v-if="loading">Carregando...</span>
      <span class="apc-error" v-if="errorMsg && !loading">{{ errorMsg }}</span>
    </div>

    <div class="apc-chart-wrap" ref="wrapEl">
      <div ref="chartEl" class="apc-chart" />
      <div class="apc-empty" v-if="!loading && !chartData.length">
        {{ errorMsg || 'Sem deslocamento suficiente para montar o grafico atemporal.' }}
      </div>
    </div>

    <div class="apc-footer">
      <span>1 candle = 10 ticks de 5 pts; bandas Linear + Non-linear com FV Core.</span>
      <span v-if="payload?.latest_capture_at">Fonte {{ formatTime(payload.latest_capture_at) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  init,
  dispose,
  CandleType,
  LineType,
  YAxisPosition,
  YAxisType,
  TooltipShowRule,
  TooltipShowType,
  CandleTooltipRectPosition,
  registerIndicator,
} from '@/vendor/equicharts/equicharts.esm.js'
import {
  getAtemporalPriceChart,
  getAtemporalPriceChartLatestPrice,
  getFairValueLegsLatestPoint,
  getFlowDeltaWindows,
  getMarketScreenChartPanel,
} from '@/api/macro.js'
import { getVolumeIvHistory } from '@/api/options.js'

const props = defineProps({
  modelData: { type: Object, default: null },
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const REQUEST_TIMEOUT_MS = 45_000
const HOT_REFRESH_MS = 1_000
const FLOW_HOT_REFRESH_MS = 5_000
const MAX_CHART_POINTS = 900
const FLOW_HISTORY_WINDOW_LIMIT = 240
const FLOW_HOT_WINDOW_LIMIT = 12
const MAX_HOT_PRICE_JUMP_POINTS = 2_000
const CACHE_KEY = 'discovery:atemporal-price-chart:latest:v1'
const CANDLE_PANE_ID = 'candle_pane'
const TRADING_DAYS_SQRT = Math.sqrt(252)
const STRESS_BAND_WEIGHTS = {
  callSkew: 0.5,
  putSkew: 0.5,
  vxbr: 0.25,
  minVolRatio: 0.55,
  linearHalfMultiplier: 0.5,
  nonLinearDoubleMultiplier: 2,
  rangeLookback: 34,
  rangeMultiplier: 8,
  stressCall: 2,
  stressPut: 2,
  stressVxbr: 1,
  minStress: 0.65,
  maxStress: 1.8,
  fairValuePressure: 0.65,
  fairValueMaxPressure: 0.85,
}

const loading = ref(false)
const errorMsg = ref('')
const payload = ref(null)
const volHistory = ref([])
const vxbrHistory = ref([])
const flowWindows = ref([])
const fairValueCore = ref(null)
const latestAtmIv = ref(null)
const chartEl = ref(null)
const wrapEl = ref(null)
let chart = null
let resizeObserver = null
let reloadTimer = null
let reloadPromise = null
let hotReloadPromise = null
let flowWindowsPromise = null
let lastHotTimestampMs = 0
let lastCachePersistAt = 0
let lastFlowRefreshAt = 0

const chartRows = computed(() => payload.value?.chart_rows || [])
const latestRow = computed(() => payload.value?.latest || chartRows.value[chartRows.value.length - 1] || null)
const resolvedAtmIv = computed(() => {
  const ctx = props.modelData?.market_context || {}
  const value = Number(latestAtmIv.value ?? ctx.iv_atm ?? ctx.atm_implied_vol ?? ctx.implied_vol ?? payload.value?.implied_vol)
  if (!Number.isFinite(value) || value <= 0) return null
  return value > 3 ? value / 100 : value
})

const flowWindowsByIndex = computed(() => {
  const mapped = new Map()
  for (const item of flowWindows.value || []) {
    mapped.set(String(item.index), item)
  }
  return mapped
})

const chartData = computed(() => {
  const rows = chartRows.value
  let carriedFlowVwap = null
  let carriedFlowRlpVwap = null
  return rows.map((row, index) => {
  const flowWindow = flowWindowsByIndex.value.get(String(row.bar_index ?? index))
  const flowSnapshot = flowWindow?.snapshot || {}
  const flowTotals = flowWindow?.totals || {}
  const currentFlowVwap = safeNumber(flowSnapshot.vwap)
  const currentFlowRlpVwap = safeNumber(flowSnapshot.rlp_vwap)
  if (currentFlowVwap != null) carriedFlowVwap = currentFlowVwap
  if (currentFlowRlpVwap != null) carriedFlowRlpVwap = currentFlowRlpVwap
  const volSnapshot = volSnapshotForTimestamp(row.timestamp_ms)
  const vxbr = vxbrSnapshotForTimestamp(row.timestamp_ms)
  const linearBand = linearVolBandForRow(row, volSnapshot, vxbr)
  const stressBand = stressAdjustedBandForRow(row, rows, index, volSnapshot, vxbr)
  const linearHalfBand = scaledBandFromBase(row.ma_271, linearBand, STRESS_BAND_WEIGHTS.linearHalfMultiplier)
  const stressDoubleBand = scaledBandFromBase(row.ma_271, stressBand, STRESS_BAND_WEIGHTS.nonLinearDoubleMultiplier)
  return {
    timestamp: row.timestamp_ms,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.sample_count || 0,
    ma271: row.ma_271,
    linearBandUpper: linearBand.upper ?? row.iv_band_upper,
    linearBandLower: linearBand.lower ?? row.iv_band_lower,
    linearHalfBandUpper: linearHalfBand.upper,
    linearHalfBandLower: linearHalfBand.lower,
    bandUpper: stressBand.upper ?? row.iv_band_upper,
    bandLower: stressBand.lower ?? row.iv_band_lower,
    bandUpper2x: stressDoubleBand.upper,
    bandLower2x: stressDoubleBand.lower,
    flowVwap: currentFlowVwap ?? carriedFlowVwap,
    flowRlpVwap: currentFlowRlpVwap ?? carriedFlowRlpVwap,
    flowBuyAggression: safeNumber(flowTotals.delta_buy_agression) ?? 0,
    flowSellAggression: safeNumber(flowTotals.delta_sell_agression) ?? 0,
    flowAggression: safeNumber(flowTotals.delta_agression_balance) ?? 0,
    flowMaker: safeNumber(flowTotals.delta_maker_balance) ?? 0,
    flowRlp: safeNumber(flowTotals.delta_rlp_balance) ?? 0,
    ...volSnapshot,
    vxbr,
  }
  })
})

function requestPayload(forceRefresh = false) {
  return {
    symbol: 'XB1',
    lookback_minutes: 10080,
    tick_size_points: 5,
    ticks_per_candle: 10,
    moving_average_points: 271,
    max_points: MAX_CHART_POINTS,
    include_partial: true,
    atm_implied_vol: resolvedAtmIv.value,
    force_refresh: Boolean(forceRefresh),
  }
}

function rowTimestamp(row) {
  const parsed = Number(row?.timestamp_ms ?? Date.parse(row?.timestamp || ''))
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeLatestPricePayload(rawPayload) {
  const data = rawPayload?.data || rawPayload
  const latest = data?.latest || data
  const price = safeNumber(latest?.price ?? latest?.close)
  const timestampMs = rowTimestamp(latest)
  if (price == null || timestampMs == null) return null
  return {
    price,
    timestamp: latest?.timestamp || new Date(timestampMs).toISOString(),
    timestamp_ms: timestampMs,
    daily_change_pct: safeNumber(latest?.daily_change_pct),
  }
}

function syncHotTimestampFromPayload() {
  const latest = payload.value?.latest || null
  const sourceEpoch = safeNumber(latest?.source_last_capture_at_epoch)
  lastHotTimestampMs = Number(latest?.source_timestamp_ms)
    || (sourceEpoch != null ? sourceEpoch * 1000 : 0)
    || rowTimestamp(latest)
    || 0
}

function recomputeAtemporalBands(rows) {
  const windowSize = Math.max(Number(payload.value?.moving_average_points || 271), 2)
  const iv = safeNumber(resolvedAtmIv.value)
  const dailyIv = iv != null && iv > 0 ? iv / Math.sqrt(252) : null
  const closes = []
  for (const row of rows) {
    const close = safeNumber(row.close)
    if (close == null) {
      row.ma_271 = null
      row.iv_band_upper = null
      row.iv_band_lower = null
      continue
    }
    closes.push(close)
    const scoped = closes.slice(-windowSize)
    if (scoped.length < windowSize) {
      row.ma_271 = null
      row.iv_band_upper = null
      row.iv_band_lower = null
      continue
    }
    const ma = scoped.reduce((sum, value) => sum + value, 0) / scoped.length
    row.ma_271 = Number(ma.toFixed(4))
    row.iv_band_upper = dailyIv != null ? Number((ma + (ma * dailyIv)).toFixed(4)) : null
    row.iv_band_lower = dailyIv != null ? Number((ma - (ma * dailyIv)).toFixed(4)) : null
  }
}

function reindexAtemporalRows(rows) {
  rows.forEach((row, index) => {
    row.bar_index = index + 1
  })
}

function buildMovementRow({
  timestampMs,
  startTimestamp,
  sessionDate,
  open,
  high,
  low,
  close,
  complete,
  sampleCount,
  targetPoints,
  sourceTimestamp,
  sourceTimestampMs,
}) {
  const movement = close - open
  return {
    timestamp: new Date(timestampMs).toISOString(),
    timestamp_ms: timestampMs,
    start_timestamp: startTimestamp,
    session_date: sessionDate,
    open: Number(open.toFixed(4)),
    high: Number(high.toFixed(4)),
    low: Number(low.toFixed(4)),
    close: Number(close.toFixed(4)),
    price: Number(close.toFixed(4)),
    direction: close >= open ? 'up' : 'down',
    complete: Boolean(complete),
    movement_points: Number(movement.toFixed(4)),
    target_points: Number(targetPoints.toFixed(4)),
    sample_count: Math.max(Number(sampleCount || 0), 1),
    source_timestamp: sourceTimestamp,
    source_timestamp_ms: sourceTimestampMs,
  }
}

function applyLatestPriceTick(tick) {
  if (!payload.value?.chart_rows?.length) return { changed: false, reset: false }
  const price = safeNumber(tick?.price)
  const tickTimestampMs = rowTimestamp(tick)
  if (price == null || tickTimestampMs == null) return { changed: false, reset: false }
  if (tickTimestampMs <= lastHotTimestampMs) return { changed: false, reset: false }

  const currentRows = Array.isArray(payload.value.chart_rows) ? payload.value.chart_rows : []
  const currentLatest = currentRows[currentRows.length - 1]
  const currentClose = safeNumber(currentLatest?.close)
  if (currentClose != null && Math.abs(price - currentClose) > MAX_HOT_PRICE_JUMP_POINTS) {
    console.debug('[AtemporalPriceChartWidget] latest price outlier skipped', { price, currentClose })
    lastHotTimestampMs = tickTimestampMs
    return { changed: false, reset: false }
  }

  const targetPoints = Math.max(Number(payload.value?.target_points || 50), 0.01)
  const hadPartial = currentLatest?.complete === false
  const rows = currentRows.slice()
  const working = hadPartial
    ? { ...rows.pop() }
    : {
        open: currentLatest.close,
        high: currentLatest.close,
        low: currentLatest.close,
        close: currentLatest.close,
        timestamp: currentLatest.timestamp,
        timestamp_ms: currentLatest.timestamp_ms,
        start_timestamp: currentLatest.timestamp,
        session_date: currentLatest.session_date,
        sample_count: 0,
      }

  let open = safeNumber(working.open)
  let high = safeNumber(working.high ?? working.open)
  let low = safeNumber(working.low ?? working.open)
  let sampleCount = Number(working.sample_count || 0) + 1
  let startTimestamp = working.start_timestamp || working.timestamp || tick.timestamp
  let sessionDate = working.session_date || currentLatest?.session_date || tick.timestamp?.slice(0, 10)
  let reset = !hadPartial
  if (open == null || high == null || low == null) return { changed: false, reset: false }

  while (Math.abs(price - open) >= targetPoints) {
    const direction = price >= open ? 1 : -1
    const close = open + (direction * targetPoints)
    const completeHigh = direction >= 0 ? Math.max(high, close) : Math.max(high, open)
    const completeLow = direction >= 0 ? Math.min(low, open) : Math.min(low, close)
    rows.push(buildMovementRow({
      timestampMs: tickTimestampMs,
      startTimestamp,
      sessionDate,
      open,
      high: completeHigh,
      low: completeLow,
      close,
      complete: true,
      sampleCount,
      targetPoints,
      sourceTimestamp: tick.timestamp,
      sourceTimestampMs: tickTimestampMs,
    }))
    open = close
    high = open
    low = open
    startTimestamp = tick.timestamp
    sessionDate = tick.timestamp?.slice(0, 10) || sessionDate
    sampleCount = 1
    reset = true
  }

  high = Math.max(high, price)
  low = Math.min(low, price)
  const previousPartialTimestamp = hadPartial ? rowTimestamp(working) : null
  const previousFinalTimestamp = rowTimestamp(rows[rows.length - 1]) || 0
  const partialTimestampMs = reset
    ? Math.max(tickTimestampMs + 1, previousFinalTimestamp + 1)
    : (previousPartialTimestamp || Math.max(tickTimestampMs, previousFinalTimestamp + 1))

  rows.push(buildMovementRow({
    timestampMs: partialTimestampMs,
    startTimestamp,
    sessionDate,
    open,
    high,
    low,
    close: price,
    complete: false,
    sampleCount,
    targetPoints,
    sourceTimestamp: tick.timestamp,
    sourceTimestampMs: tickTimestampMs,
  }))

  const trimmedRows = rows.slice(-MAX_CHART_POINTS)
  reindexAtemporalRows(trimmedRows)
  recomputeAtemporalBands(trimmedRows)
  payload.value = {
    ...payload.value,
    latest_capture_at: tick.timestamp,
    chart_rows: trimmedRows,
    latest: trimmedRows[trimmedRows.length - 1],
  }
  lastHotTimestampMs = tickTimestampMs
  return { changed: true, reset }
}

function withTimeout(promise, label, timeoutMs = REQUEST_TIMEOUT_MS) {
  let timerId = null
  const timeoutPromise = new Promise((_, reject) => {
    timerId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timerId) clearTimeout(timerId)
  })
}

function finite(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

let indicatorsRegistered = false
function ensureIndicators() {
  if (indicatorsRegistered) return
  registerIndicator({
    name: 'ATEMPORAL_IV_BANDS',
    shortName: 'IV Band',
    series: 'price',
    precision: 2,
    shouldOhlc: false,
    figures: [
      { key: 'ma', title: 'MA271: ', type: 'line' },
      { key: 'upper', title: 'NL +: ', type: 'line' },
      { key: 'lower', title: 'NL -: ', type: 'line' },
      { key: 'upper2x', title: 'NL2 +: ', type: 'line' },
      { key: 'lower2x', title: 'NL2 -: ', type: 'line' },
      { key: 'linearUpper', title: 'Lin +: ', type: 'line' },
      { key: 'linearLower', title: 'Lin -: ', type: 'line' },
      { key: 'linearHalfUpper', title: 'Lin0.5 +: ', type: 'line' },
      { key: 'linearHalfLower', title: 'Lin0.5 -: ', type: 'line' },
      { key: 'vwap', title: 'VWAP: ', type: 'line' },
    ],
    calc: data => data.map(item => ({
      ma: finite(item.ma271),
      upper: finite(item.bandUpper),
      lower: finite(item.bandLower),
      upper2x: finite(item.bandUpper2x),
      lower2x: finite(item.bandLower2x),
      linearUpper: finite(item.linearBandUpper),
      linearLower: finite(item.linearBandLower),
      linearHalfUpper: finite(item.linearHalfBandUpper),
      linearHalfLower: finite(item.linearHalfBandLower),
      vwap: finite(item.flowVwap),
    })),
  })
  registerIndicator({
    name: 'ATEMPORAL_FLOW_AGGRESSION',
    shortName: 'Agressao',
    precision: 0,
    shouldOhlc: false,
    figures: [
      { key: 'buy', title: 'Compra: ', type: 'bar' },
      { key: 'sell', title: 'Venda: ', type: 'bar' },
      { key: 'balance', title: 'Saldo: ', type: 'line' },
    ],
    calc: data => data.map(item => {
      const buy = finite(item.flowBuyAggression)
      const sell = finite(item.flowSellAggression)
      return {
        buy: buy == null ? undefined : Math.max(buy, 0),
        sell: sell == null ? undefined : -Math.max(sell, 0),
        balance: finite(item.flowAggression),
      }
    }),
  })
  registerIndicator({
    name: 'ATEMPORAL_VOL_HISTORY',
    shortName: 'Vols',
    precision: 4,
    minValue: 0,
    figures: [
      { key: 'atm', title: 'ATM: ', type: 'line' },
      { key: 'call25', title: '25DC: ', type: 'line' },
      { key: 'put25', title: '25DP: ', type: 'line' },
    ],
    calc: data => data.map(item => ({
      atm: finite(item.volAtm),
      call25: finite(item.vol25Call),
      put25: finite(item.vol25Put),
    })),
  })
  indicatorsRegistered = true
}

function safeNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeVolValue(value) {
  const parsed = safeNumber(value)
  if (parsed == null || parsed <= 0) return null
  return parsed > 3 ? parsed / 100 : parsed
}

function stdev(values) {
  if (!values.length) return null
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length
  return Math.sqrt(variance)
}

function normalizeVolHistory(rows) {
  const sorted = (rows || [])
    .map(item => ({
      timestampMs: Date.parse(item?.captured_at || item?.timestamp || item?.date || ''),
      ivAtm: normalizeVolValue(item?.iv_atm ?? item?.iv_interpolated),
      iv25Call: normalizeVolValue(item?.iv_25d_call),
      iv25Put: normalizeVolValue(item?.iv_25d_put),
    }))
    .filter(item => Number.isFinite(item.timestampMs) && item.ivAtm != null)
    .sort((left, right) => left.timestampMs - right.timestampMs)

  const deltas = []
  return sorted.map((item, index) => {
    if (index > 0) {
      const previous = sorted[index - 1]
      if (previous?.ivAtm != null && item.ivAtm != null) {
        deltas.push(item.ivAtm - previous.ivAtm)
      }
    }
    const scoped = deltas.slice(-30)
    const volOfVol = scoped.length >= 3 ? stdev(scoped) * Math.sqrt(252) : null
    return { ...item, volOfVol }
  })
}

function volSnapshotForTimestamp(timestampMs) {
  const target = Number(timestampMs)
  if (!Number.isFinite(target) || !volHistory.value.length) {
    return { volOfVol: null, volAtm: null, vol25Call: null, vol25Put: null }
  }
  let selected = null
  for (const item of volHistory.value) {
    if (item.timestampMs <= target) selected = item
    if (item.timestampMs > target) break
  }
  selected ||= volHistory.value[volHistory.value.length - 1]
  return {
    volOfVol: selected?.volOfVol ?? null,
    volAtm: selected?.ivAtm ?? null,
    vol25Call: selected?.iv25Call ?? null,
    vol25Put: selected?.iv25Put ?? null,
  }
}

function normalizeVxbrHistory(rows) {
  return (rows || [])
    .map(item => ({
      timestampMs: Date.parse(item?.timestamp || item?.captured_at || ''),
      value: normalizeVolValue(item?.price ?? item?.close ?? item?.value),
    }))
    .filter(item => Number.isFinite(item.timestampMs) && item.value != null)
    .sort((left, right) => left.timestampMs - right.timestampMs)
}

function vxbrSnapshotForTimestamp(timestampMs) {
  const target = Number(timestampMs)
  if (!Number.isFinite(target) || !vxbrHistory.value.length) return null
  let selected = null
  for (const item of vxbrHistory.value) {
    if (item.timestampMs <= target) selected = item
    if (item.timestampMs > target) break
  }
  selected ||= vxbrHistory.value[vxbrHistory.value.length - 1]
  return selected?.value ?? null
}

function clamp(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value))
}

function recentAtemporalRange(rows, index) {
  const start = Math.max(0, index - STRESS_BAND_WEIGHTS.rangeLookback + 1)
  const scoped = rows
    .slice(start, index + 1)
    .map(item => {
      const high = safeNumber(item?.high)
      const low = safeNumber(item?.low)
      if (high == null || low == null) return null
      return Math.abs(high - low)
    })
    .filter(value => value != null && value > 0)
  if (!scoped.length) return null
  const alpha = 2 / (Math.min(scoped.length, STRESS_BAND_WEIGHTS.rangeLookback) + 1)
  return scoped.reduce((ema, value, itemIndex) => (
    itemIndex === 0 ? value : ((alpha * value) + ((1 - alpha) * ema))
  ), scoped[0])
}

function linearVolBandForRow(row, volSnapshot, vxbr) {
  const base = safeNumber(row?.ma_271)
  const atm = normalizeVolValue(volSnapshot?.volAtm)
  if (base == null || base <= 0 || atm == null) {
    return { upper: null, lower: null }
  }

  const call25 = normalizeVolValue(volSnapshot?.vol25Call)
  const put25 = normalizeVolValue(volSnapshot?.vol25Put)
  const normalizedVxbr = normalizeVolValue(vxbr)
  const callSkewStress = (call25 ?? atm) - atm
  const putSkewStress = (put25 ?? atm) - atm
  const vxbrStress = (normalizedVxbr ?? atm) - atm
  const minVol = atm * STRESS_BAND_WEIGHTS.minVolRatio
  const volUp =
    atm +
    STRESS_BAND_WEIGHTS.callSkew * callSkewStress +
    STRESS_BAND_WEIGHTS.vxbr * vxbrStress
  const volDown =
    atm +
    STRESS_BAND_WEIGHTS.putSkew * putSkewStress +
    STRESS_BAND_WEIGHTS.vxbr * vxbrStress
  return {
    upper: base + (base * Math.max(volUp, minVol) / TRADING_DAYS_SQRT),
    lower: base - (base * Math.max(volDown, minVol) / TRADING_DAYS_SQRT),
  }
}

function scaledBandFromBase(baseValue, band, multiplier) {
  const base = safeNumber(baseValue)
  const upper = safeNumber(band?.upper)
  const lower = safeNumber(band?.lower)
  if (base == null || base <= 0) return { upper: null, lower: null }
  return {
    upper: upper == null ? null : base + ((upper - base) * multiplier),
    lower: lower == null ? null : base - ((base - lower) * multiplier),
  }
}

function fairValueCorePressureDelta(referenceDelta) {
  const snapshot = fairValueCore.value || {}
  const core = safeNumber(snapshot.core)
  const previousClose = safeNumber(snapshot.previousClose)
  const reference = Math.max(safeNumber(referenceDelta) ?? 0, 1)
  if (core == null || previousClose == null) return { up: 0, down: 0 }

  const gap = core - previousClose
  const magnitude = Math.abs(gap)
  if (magnitude <= 0) return { up: 0, down: 0 }

  const cappedPressure = reference *
    STRESS_BAND_WEIGHTS.fairValueMaxPressure *
    Math.tanh(magnitude / reference)
  const directionalDelta = cappedPressure * STRESS_BAND_WEIGHTS.fairValuePressure
  return gap > 0
    ? { up: directionalDelta, down: 0 }
    : { up: 0, down: directionalDelta }
}

function stressAdjustedBandForRow(row, rows, index, volSnapshot, vxbr) {
  const base = safeNumber(row?.ma_271)
  const atm = normalizeVolValue(volSnapshot?.volAtm)
  const baseRange = recentAtemporalRange(rows, index)
  if (base == null || base <= 0 || atm == null || baseRange == null) {
    return { upper: null, lower: null }
  }

  const call25 = normalizeVolValue(volSnapshot?.vol25Call)
  const put25 = normalizeVolValue(volSnapshot?.vol25Put)
  const normalizedVxbr = normalizeVolValue(vxbr)
  const callSkewStress = (call25 ?? atm) - atm
  const putSkewStress = (put25 ?? atm) - atm
  const vxbrStress = (normalizedVxbr ?? atm) - atm
  const stressUp = clamp(
    1 +
      STRESS_BAND_WEIGHTS.stressCall * callSkewStress +
      STRESS_BAND_WEIGHTS.stressVxbr * vxbrStress,
    STRESS_BAND_WEIGHTS.minStress,
    STRESS_BAND_WEIGHTS.maxStress,
  )
  const stressDown = clamp(
    1 +
      STRESS_BAND_WEIGHTS.stressPut * putSkewStress +
      STRESS_BAND_WEIGHTS.stressVxbr * vxbrStress,
    STRESS_BAND_WEIGHTS.minStress,
    STRESS_BAND_WEIGHTS.maxStress,
  )
  const referenceDelta = baseRange * STRESS_BAND_WEIGHTS.rangeMultiplier
  const fairValuePressure = fairValueCorePressureDelta(referenceDelta)
  const deltaUp = referenceDelta * stressUp + fairValuePressure.up
  const deltaDown = referenceDelta * stressDown + fairValuePressure.down
  return {
    upper: base + deltaUp,
    lower: base - deltaDown,
  }
}

function epochFromValue(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  if (Number.isFinite(numeric)) {
    return numeric > 10_000_000_000 ? numeric / 1000 : numeric
  }
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed / 1000 : null
}

function buildFlowWindows(limit = FLOW_HISTORY_WINDOW_LIMIT) {
  const rows = chartRows.value || []
  const visibleRows = rows.slice(-limit)
  const offset = Math.max(rows.length - visibleRows.length, 0)
  return visibleRows
    .map((row, localIndex) => {
      const index = offset + localIndex
      const previous = rows[index - 1]
      const startEpoch =
        epochFromValue(row.start_timestamp) ??
        epochFromValue(row.start_timestamp_ms) ??
        epochFromValue(previous?.timestamp_ms)
      const endEpoch =
        epochFromValue(row.end_timestamp) ??
        epochFromValue(row.timestamp_ms) ??
        epochFromValue(row.timestamp)
      if (startEpoch == null || endEpoch == null || endEpoch <= startEpoch) return null
      return {
        index: row.bar_index ?? index,
        start_epoch: startEpoch,
        end_epoch: endEpoch,
      }
    })
    .filter(Boolean)
}

function mergeFlowWindows(rows) {
  const merged = new Map()
  for (const item of flowWindows.value || []) {
    if (item?.index != null) merged.set(String(item.index), item)
  }
  for (const item of rows || []) {
    if (item?.index != null) merged.set(String(item.index), item)
  }
  const orderedWindows = buildFlowWindows(FLOW_HISTORY_WINDOW_LIMIT)
  flowWindows.value = orderedWindows
    .map(item => merged.get(String(item.index)))
    .filter(Boolean)
}

async function loadFlowWindows({ hot = false } = {}) {
  if (flowWindowsPromise) return flowWindowsPromise
  const windows = buildFlowWindows(hot ? FLOW_HOT_WINDOW_LIMIT : FLOW_HISTORY_WINDOW_LIMIT)
  if (!windows.length) {
    if (!hot) flowWindows.value = []
    return
  }
  flowWindowsPromise = (async () => {
    try {
      const res = await getFlowDeltaWindows({
        windows,
        agent_limit: 0,
      })
      const rows = res?.data || []
      const normalized = Array.isArray(rows) ? rows : []
      if (hot) {
        mergeFlowWindows(normalized)
      } else {
        flowWindows.value = normalized
      }
      await nextTick()
      refreshChartData({ reset: true })
    } catch (error) {
      console.debug('[AtemporalPriceChartWidget] flow windows unavailable', error)
    } finally {
      flowWindowsPromise = null
    }
  })()
  return flowWindowsPromise
}

function refreshFlowWindowsThrottled() {
  if ((Date.now() - lastFlowRefreshAt) < FLOW_HOT_REFRESH_MS) return
  lastFlowRefreshAt = Date.now()
  loadFlowWindows({ hot: true })
  loadFairValueCore()
}

async function loadVolHistory() {
  try {
    const res = await getVolumeIvHistory({
      underlying_security: props.underlyingSecurity || 'IBOVE Index',
      limit: 720,
    })
    const history = res?.data?.history || res?.history || []
    const normalized = normalizeVolHistory(history)
    if (normalized.length) {
      volHistory.value = normalized
      await nextTick()
      refreshChartData({ reset: true })
    }
    const latest = normalized
      .slice()
      .reverse()
      .map(item => item.ivAtm)
      .find(value => value != null && value > 0)
    if (latest != null) {
      latestAtmIv.value = latest
    }
  } catch (error) {
    console.debug('[AtemporalPriceChartWidget] vol history unavailable', error)
  }
}

async function loadVxbrHistory() {
  try {
    const res = await getMarketScreenChartPanel({
      symbol: 'VXBR',
      benchmark_symbol: 'XB1',
      lookback_minutes: 10080,
      max_points: MAX_CHART_POINTS,
      include_assets: false,
    })
    const rows = res?.data?.series?.price_points || res?.series?.price_points || []
    const normalized = normalizeVxbrHistory(rows)
    if (normalized.length) {
      vxbrHistory.value = normalized
      await nextTick()
      refreshChartData({ reset: true })
    }
  } catch (error) {
    console.debug('[AtemporalPriceChartWidget] VXBR history unavailable', error)
  }
}

async function loadFairValueCore() {
  try {
    const res = await getFairValueLegsLatestPoint({
      sessions: 3,
      bar_minutes: 5,
      session_start: '09:00',
      session_end: '18:30',
      rolling_window_points: 60,
      config: {},
      force_refresh: false,
    })
    const data = res?.data || res
    const row = data?.latest || (Array.isArray(data?.chart_rows) ? data.chart_rows[data.chart_rows.length - 1] : null) || data
    const core = safeNumber(row?.fair_value_core ?? row?.core_fair_value ?? row?.core)
    const previousClose = safeNumber(
      row?.previous_close ??
      row?.prev_close ??
      row?.previous_session_close ??
      row?.prior_close ??
      data?.previous_close ??
      data?.previous_session_close ??
      row?.close
    )
    if (core != null && previousClose != null) {
      fairValueCore.value = {
        core,
        previousClose,
        timestamp: row?.timestamp || data?.generated_at || null,
      }
      await nextTick()
      refreshChartData({ reset: true })
    }
  } catch (error) {
    console.debug('[AtemporalPriceChartWidget] fair value core unavailable', error)
  }
}

async function reload({ background = false, forceRefresh = false } = {}) {
  if (reloadPromise) return reloadPromise
  reloadPromise = runReload({ background, forceRefresh }).finally(() => {
    reloadPromise = null
  })
  return reloadPromise
}

async function runReload({ background = false, forceRefresh = false } = {}) {
  if (!background) loading.value = true
  if (!background || !payload.value?.chart_rows?.length) errorMsg.value = ''
  try {
    const res = await withTimeout(
      getAtemporalPriceChart(requestPayload(forceRefresh)),
      'Grafico atemporal',
    )
    const nextPayload = res?.data || res
    if (!Array.isArray(nextPayload?.chart_rows) || !nextPayload.chart_rows.length) {
      throw new Error(nextPayload?.status || 'Payload atemporal vazio')
    }
    payload.value = nextPayload
    syncHotTimestampFromPayload()
    persistCache({ force: true })
    await nextTick()
    refreshChartData({ reset: true, scrollToLatest: true })
    lastFlowRefreshAt = Date.now()
    loadFlowWindows()
    loadFairValueCore()
    refreshLatest()
  } catch (error) {
    if (payload.value?.chart_rows?.length) {
      errorMsg.value = 'Atualizacao lenta; mantendo ultimo snapshot'
    } else {
      errorMsg.value = error?.message || 'Erro ao carregar grafico atemporal'
    }
    console.error('[AtemporalPriceChartWidget] load error', error)
  } finally {
    loading.value = false
  }
}

async function refreshLatest() {
  if (hotReloadPromise) return hotReloadPromise
  hotReloadPromise = runRefreshLatest().finally(() => {
    hotReloadPromise = null
  })
  return hotReloadPromise
}

async function runRefreshLatest() {
  if (!payload.value?.chart_rows?.length) return
  try {
    const res = await withTimeout(
      getAtemporalPriceChartLatestPrice({ symbol: 'XB1' }),
      'Ultimo preco XB1',
      3_000,
    )
    const tick = normalizeLatestPricePayload(res)
    const applied = applyLatestPriceTick(tick)
    if (applied.changed) {
      persistCache()
      await nextTick()
      refreshChartData({ reset: applied.reset, scrollToLatest: true })
      refreshFlowWindowsThrottled()
      if (errorMsg.value === 'Atualizacao lenta; mantendo ultimo snapshot') errorMsg.value = ''
    }
  } catch (error) {
    console.debug('[AtemporalPriceChartWidget] hot update skipped', error)
  }
}

function persistCache({ force = false } = {}) {
  if (typeof window === 'undefined') return
  try {
    if (!payload.value?.chart_rows?.length) return
    if (!force && (Date.now() - lastCachePersistAt) < 10_000) return
    lastCachePersistAt = Date.now()
    window.localStorage.setItem(CACHE_KEY, JSON.stringify({
      savedAt: Date.now(),
      payload: payload.value,
    }))
  } catch {}
}

function restoreCache() {
  if (typeof window === 'undefined') return false
  try {
    const raw = window.localStorage.getItem(CACHE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    if (!parsed?.payload?.chart_rows?.length) return false
    if ((Date.now() - Number(parsed.savedAt || 0)) > 24 * 60 * 60 * 1000) return false
    payload.value = parsed.payload
    syncHotTimestampFromPayload()
    return true
  } catch {
    return false
  }
}

function mountChart() {
  destroyChart()
  if (!chartEl.value || !chartData.value.length) return
  ensureIndicators()
  chart = init(chartEl.value, {
    timezone: 'America/Sao_Paulo',
    yScrolling: false,
    styles: buildStyles(),
    layout: [
      { type: 'candle' },
      { type: 'xAxis', options: { position: 'bottom' } },
    ],
  })
  if (!chart) return
  chart.applyNewData(chartData.value, true)
  chart.createIndicator(
    { name: 'ATEMPORAL_IV_BANDS', styles: { lines: bandLineStyles() } },
    true,
    { id: CANDLE_PANE_ID },
  )
  chart.createIndicator(
    { name: 'ATEMPORAL_FLOW_AGGRESSION', styles: flowAggressionStyles() },
    false,
    { height: 118 },
  )
  chart.createIndicator(
    { name: 'ATEMPORAL_VOL_HISTORY', styles: { lines: volLineStyles() } },
    false,
    { height: 132 },
  )
  chart.scrollToRealTime()
  chart.resize()
}

function refreshChartData({ reset = false, scrollToLatest = false } = {}) {
  if (!chartData.value.length) {
    destroyChart()
    return
  }
  if (!chart) {
    mountChart()
    return
  }
  if (reset) {
    chart.clearData()
    chart.applyNewData(chartData.value, true)
  } else {
    const last = chartData.value[chartData.value.length - 1]
    if (last) chart.updateData(last)
  }
  if (scrollToLatest) chart.scrollToRealTime()
  chart.resize()
}

function destroyChart() {
  if (!chart) return
  try { dispose(chartEl.value) } catch {}
  chart = null
}

function bandLineStyles() {
  return [
    { color: '#e2e8f0', size: 1.4, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
    { color: 'rgba(56,189,248,0.92)', size: 1.3, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
    { color: 'rgba(251,113,133,0.92)', size: 1.3, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
    { color: 'rgba(56,189,248,0.58)', size: 1.0, style: LineType.Dashed, dashedValue: [3, 5], smooth: false },
    { color: 'rgba(251,113,133,0.58)', size: 1.0, style: LineType.Dashed, dashedValue: [3, 5], smooth: false },
    { color: 'rgba(56,189,248,0.45)', size: 0.95, style: LineType.Dashed, dashedValue: [7, 5], smooth: false },
    { color: 'rgba(251,113,133,0.45)', size: 0.95, style: LineType.Dashed, dashedValue: [7, 5], smooth: false },
    { color: 'rgba(125,211,252,0.34)', size: 0.85, style: LineType.Dashed, dashedValue: [2, 7], smooth: false },
    { color: 'rgba(252,165,165,0.34)', size: 0.85, style: LineType.Dashed, dashedValue: [2, 7], smooth: false },
    { color: 'rgba(245,158,11,0.95)', size: 1.15, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
  ]
}

function volLineStyles() {
  return [
    { color: '#38bdf8', size: 1.25, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
    { color: '#22c55e', size: 1.05, style: LineType.Dashed, dashedValue: [5, 4], smooth: false },
    { color: '#fb7185', size: 1.05, style: LineType.Dashed, dashedValue: [5, 4], smooth: false },
  ]
}

function flowAggressionStyles() {
  return {
    bars: [
      { color: 'rgba(34,197,94,0.72)', borderColor: 'rgba(34,197,94,0.92)', borderSize: 0 },
      { color: 'rgba(248,113,113,0.72)', borderColor: 'rgba(248,113,113,0.92)', borderSize: 0 },
    ],
    lines: [
      { color: '#f8fafc', size: 1.25, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
    ],
  }
}

function buildStyles() {
  return {
    grid: {
      show: true,
      horizontal: { show: true, size: 1, color: 'rgba(148,163,184,0.10)', style: LineType.Dashed, dashedValue: [4, 6] },
      vertical: { show: true, size: 1, color: 'rgba(148,163,184,0.06)', style: LineType.Dashed, dashedValue: [4, 8] },
    },
    candle: {
      type: CandleType.CandleSolid,
      bar: {
        upColor: '#22c55e',
        downColor: '#ef4444',
        noChangeColor: '#94a3b8',
        upBorderColor: '#16a34a',
        downBorderColor: '#dc2626',
        noChangeBorderColor: '#64748b',
        upWickColor: '#16a34a',
        downWickColor: '#dc2626',
        noChangeWickColor: '#64748b',
      },
      priceMark: {
        show: true,
        high: { show: false },
        low: { show: false },
        last: {
          show: true,
          upColor: '#22c55e',
          downColor: '#ef4444',
          noChangeColor: '#94a3b8',
          line: { show: true, style: LineType.Dashed, dashedValue: [5, 6], size: 1 },
          text: {
            show: true,
            style: 'fill',
            size: 11,
            paddingLeft: 6,
            paddingTop: 4,
            paddingRight: 6,
            paddingBottom: 4,
            borderSize: 0,
            borderColor: 'transparent',
            borderRadius: 6,
            color: '#08111f',
            family: '"JetBrains Mono", monospace',
            weight: 'bold',
          },
        },
      },
      tooltip: {
        showRule: TooltipShowRule.FollowCross,
        showType: TooltipShowType.Standard,
        defaultValue: '--',
        custom: [
          { title: 'H', value: '{high}' },
          { title: 'O', value: '{open}' },
          { title: 'C', value: '{close}' },
          { title: 'L', value: '{low}' },
        ],
        rect: {
          position: CandleTooltipRectPosition.Fixed,
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 6,
          paddingBottom: 6,
          offsetLeft: 6,
          offsetTop: 6,
          offsetRight: 6,
          offsetBottom: 6,
          borderRadius: 8,
          borderSize: 1,
          borderColor: 'rgba(148,163,184,0.24)',
          color: '#07111f',
        },
        text: {
          size: 11,
          family: '"JetBrains Mono", monospace',
          weight: 'normal',
          color: '#d7e6f5',
          marginLeft: 6,
          marginTop: 4,
          marginRight: 8,
          marginBottom: 4,
        },
        icons: [],
      },
    },
    indicator: {
      lines: bandLineStyles(),
      lastValueMark: {
        show: true,
        text: {
          show: true,
          color: '#dbeafe',
          backgroundColor: '#08111f',
          size: 10,
          paddingLeft: 5,
          paddingRight: 5,
          paddingTop: 3,
          paddingBottom: 3,
          borderRadius: 4,
        },
      },
    },
    xAxis: {
      show: true,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView: { show: true, size: 1, length: 3, color: 'rgba(148,163,184,0.18)' },
      tickText: { show: true, color: '#8aa2b7', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 },
    },
    yAxis: {
      show: true,
      position: YAxisPosition.Right,
      type: YAxisType.Normal,
      inside: false,
      reverse: false,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView: { show: true, size: 1, length: 2, color: 'rgba(148,163,184,0.18)' },
      tickText: { show: true, color: '#dbe7f3', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 },
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.28)' },
      },
      vertical: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.24)' },
      },
    },
  }
}

function formatPrice(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '--'
  return Math.round(parsed).toLocaleString('pt-BR')
}

function formatPct(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '--'
  return `${(parsed * 100).toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(value))
  } catch {
    return String(value)
  }
}

onMounted(async () => {
  await nextTick()
  Promise.allSettled([loadVolHistory(), loadVxbrHistory(), loadFairValueCore()])
  const restored = restoreCache()
  if (restored) {
    await nextTick()
    refreshChartData({ reset: true, scrollToLatest: true })
  }
  await reload({ background: restored })
  reloadTimer = setInterval(() => refreshLatest(), HOT_REFRESH_MS)
  if (wrapEl.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(wrapEl.value)
  }
})

onUnmounted(() => {
  clearInterval(reloadTimer)
  resizeObserver?.disconnect()
  destroyChart()
})

watch(resolvedAtmIv, (next, previous) => {
  if (next !== previous) reload({ background: true, forceRefresh: true })
})

watch(() => props.refreshNonce, async () => {
  await Promise.allSettled([loadVolHistory(), loadVxbrHistory(), loadFairValueCore()])
  reload({ background: true })
})
</script>

<style scoped>
.apc-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 7px;
  background: #06111e;
  color: #dbeafe;
}

.apc-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.apc-badge,
.apc-pill,
.apc-btn,
.apc-meta {
  font-family: "JetBrains Mono", monospace;
}

.apc-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 900;
  border: 1px solid rgba(56, 189, 248, 0.36);
  color: #bae6fd;
  background: rgba(14, 165, 233, 0.14);
}

.apc-pill,
.apc-meta {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 800;
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.72);
}

.apc-pill.vol {
  color: #fed7aa;
  border-color: rgba(251, 146, 60, 0.28);
  background: rgba(154, 52, 18, 0.20);
}

.apc-btn {
  border: 1px solid rgba(148, 163, 184, 0.20);
  background: rgba(15, 23, 42, 0.86);
  color: #dbeafe;
  border-radius: 6px;
  padding: 4px 9px;
  font-size: 10px;
  font-weight: 800;
  cursor: pointer;
}

.apc-btn:hover {
  border-color: rgba(56, 189, 248, 0.46);
  color: #f8fafc;
}

.apc-spacer {
  flex: 1;
}

.apc-loading,
.apc-error {
  font-size: 10px;
  color: #93c5fd;
}

.apc-error {
  color: #fca5a5;
}

.apc-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}

.apc-chart {
  width: 100%;
  height: 100%;
}

.apc-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
  padding: 18px;
  pointer-events: none;
}

.apc-footer {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  flex-shrink: 0;
  color: #7890a8;
  font-size: 10px;
  line-height: 1.3;
  font-family: "JetBrains Mono", monospace;
}
</style>
